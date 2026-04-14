from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from moredakka.util import run_command, safe_read_text, truncate_middle


DOC_CANDIDATES = ["README.md", "AGENTS.md", "PLAN.md", "TODO.md", "SPEC.md", "DESIGN.md"]


@dataclass
class DocSnippet:
    path: str
    excerpt: str


@dataclass
class FileExcerpt:
    path: str
    excerpt: str


@dataclass
class ContextPacket:
    cwd: str
    repo_root: str | None
    mode: str
    objective: str
    inferred_objective: str
    base_ref: str
    branch: str | None
    status_summary: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    diff_stats: str = ""
    diff_excerpt: str = ""
    recent_commits: list[str] = field(default_factory=list)
    docs: list[DocSnippet] = field(default_factory=list)
    file_excerpts: list[FileExcerpt] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _git(args: list[str], cwd: Path) -> str:
    result = run_command(["git", *args], cwd=cwd)
    if result.returncode != 0:
        return ""
    return result.stdout.rstrip("\n")


def _find_repo_root(cwd: Path) -> Path | None:
    root = _git(["rev-parse", "--show-toplevel"], cwd)
    if not root:
        return None
    return Path(root).resolve()


def _collect_docs(cwd: Path, repo_root: Path | None, max_docs: int = 6) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    cur = cwd
    stop = repo_root or cwd
    while True:
        for name in DOC_CANDIDATES:
            candidate = cur / name
            if candidate.exists() and candidate not in seen:
                out.append(candidate)
                seen.add(candidate)
                if len(out) >= max_docs:
                    return out
        skill_dir = cur / ".agents" / "skills"
        if skill_dir.exists():
            for skill_manifest in sorted(skill_dir.glob("*/SKILL.md")):
                if skill_manifest not in seen:
                    out.append(skill_manifest)
                    seen.add(skill_manifest)
                    if len(out) >= max_docs:
                        return out
        if cur == stop or cur.parent == cur:
            break
        cur = cur.parent
    if repo_root and repo_root != cwd:
        for name in DOC_CANDIDATES:
            candidate = repo_root / name
            if candidate.exists() and candidate not in seen:
                out.append(candidate)
                seen.add(candidate)
                if len(out) >= max_docs:
                    return out
    return out[:max_docs]


def _parse_status(status_output: str) -> list[str]:
    lines = []
    for raw in status_output.splitlines():
        raw = raw.rstrip()
        if not raw:
            continue
        code = raw[:2].strip() or "??"
        path = raw[3:].strip() if len(raw) > 3 else raw
        lines.append(f"{code} {path}")
    return lines


def _expand_changed_path(root: Path, rel_path: str, *, limit: int) -> list[str]:
    candidate = root / rel_path
    if not candidate.exists() or candidate.is_file():
        return [rel_path]

    expanded: list[str] = []
    for path in sorted(candidate.rglob("*")):
        if path.is_dir():
            continue
        expanded.append(str(path.relative_to(root)))
        if len(expanded) >= limit:
            break
    return expanded or [rel_path]


def _select_changed_files(root: Path, status_lines: list[str], limit: int = 12) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for line in status_lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        remaining = max(0, limit - len(files))
        if remaining == 0:
            break
        for rel_path in _expand_changed_path(root, parts[1], limit=remaining):
            if rel_path in seen:
                continue
            seen.add(rel_path)
            files.append(rel_path)
            if len(files) >= limit:
                break
    return files[:limit]


def _working_diff(cwd: Path) -> str:
    parts: list[str] = []
    unstaged = _git(["diff", "--unified=3", "--no-ext-diff"], cwd)
    staged = _git(["diff", "--cached", "--unified=3", "--no-ext-diff"], cwd)
    if staged:
        parts.append("## staged diff\n" + staged)
    if unstaged:
        parts.append("## unstaged diff\n" + unstaged)
    return "\n\n".join(parts)


def _review_merge_base(cwd: Path, base_ref: str) -> str:
    merge_base = _git(["merge-base", "HEAD", base_ref], cwd)
    if not merge_base:
        raise RuntimeError(
            f"Unable to compute review diff against base ref '{base_ref}'. Check that the ref exists locally."
        )
    return merge_base


def _review_diff(cwd: Path, base_ref: str) -> tuple[str, str]:
    merge_base = _review_merge_base(cwd, base_ref)
    diff_stats = _git(["diff", "--stat", f"{merge_base}..HEAD"], cwd)
    diff_excerpt = _git(["diff", "--unified=3", f"{merge_base}..HEAD"], cwd)
    return diff_stats, diff_excerpt


def _review_changed_files(cwd: Path, base_ref: str, limit: int = 12) -> list[str]:
    merge_base = _review_merge_base(cwd, base_ref)
    output = _git(["diff", "--name-only", f"{merge_base}..HEAD"], cwd)
    files: list[str] = []
    seen: set[str] = set()
    for rel_path in output.splitlines():
        rel_path = rel_path.strip()
        if not rel_path or rel_path in seen:
            continue
        seen.add(rel_path)
        files.append(rel_path)
        if len(files) >= limit:
            break
    return files


def _recent_commits(cwd: Path, limit: int = 8) -> list[str]:
    output = _git(["log", f"--max-count={limit}", "--date=short", "--pretty=format:%h %ad %s"], cwd)
    return [line for line in output.splitlines() if line.strip()]


def _infer_objective(objective: str | None, branch: str | None, changed_files: list[str]) -> str:
    if objective:
        return objective
    if changed_files:
        joined = ", ".join(changed_files[:4])
        if branch and branch not in {"main", "master"}:
            return f"Advance branch {branch} by resolving the current work in {joined}"
        return f"Advance the current working changes in {joined}"
    if branch and branch not in {"main", "master"}:
        return f"Figure out the best next move for branch {branch}"
    return "Figure out the best next move in the current working directory"


def _collect_file_excerpts(root: Path, changed_files: list[str], per_file_chars: int = 1200) -> list[FileExcerpt]:
    excerpts: list[FileExcerpt] = []
    for rel in changed_files[:6]:
        path = root / rel
        if not path.exists() or path.is_dir():
            continue
        text = safe_read_text(path, max_chars=per_file_chars)
        if not text:
            continue
        excerpts.append(FileExcerpt(path=rel, excerpt=text))
    return excerpts


def _display_path(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def build_context_packet(
    *,
    cwd: Path,
    mode: str,
    objective: str | None,
    base_ref: str,
    char_budget: int,
) -> ContextPacket:
    repo_root = _find_repo_root(cwd)
    branch = _git(["branch", "--show-current"], cwd) if repo_root else None

    status_output = _git(["status", "--porcelain=v1"], cwd) if repo_root else ""
    status_summary = _parse_status(status_output)

    if repo_root and mode == "review":
        changed_files = _review_changed_files(cwd, base_ref)
        diff_stats, diff_excerpt = _review_diff(cwd, base_ref)
    else:
        changed_files = _select_changed_files(repo_root or cwd, status_summary)
        diff_stats = _git(["diff", "--stat", "--cached"], cwd) if repo_root else ""
        working_stats = _git(["diff", "--stat"], cwd) if repo_root else ""
        diff_stats = "\n".join([part for part in [diff_stats, working_stats] if part]).strip()
        diff_excerpt = _working_diff(cwd) if repo_root else ""

    recent_commits = _recent_commits(cwd) if repo_root else []
    inferred = _infer_objective(objective, branch, changed_files)
    docs = []
    for doc_path in _collect_docs(cwd, repo_root):
        excerpt = safe_read_text(doc_path, max_chars=2000)
        if excerpt:
            docs.append(DocSnippet(path=_display_path(doc_path, repo_root or cwd), excerpt=excerpt))

    file_excerpts = _collect_file_excerpts(repo_root or cwd, changed_files)
    packet = ContextPacket(
        cwd=str(cwd),
        repo_root=str(repo_root) if repo_root else None,
        mode=mode,
        objective=objective or "",
        inferred_objective=inferred,
        base_ref=base_ref,
        branch=branch or None,
        status_summary=status_summary,
        changed_files=changed_files,
        diff_stats=diff_stats,
        diff_excerpt=truncate_middle(diff_excerpt, max(3000, int(char_budget * 0.45))),
        recent_commits=recent_commits,
        docs=docs,
        file_excerpts=file_excerpts,
    )
    return packet


def render_context_packet(packet: ContextPacket, *, char_budget: int) -> str:
    sections: list[str] = []
    meta = [
        f"mode: {packet.mode}",
        f"cwd: {packet.cwd}",
        f"repo_root: {packet.repo_root or '(none)'}",
        f"branch: {packet.branch or '(none)'}",
        f"base_ref: {packet.base_ref}",
        f"objective: {packet.objective or '(not explicitly provided)'}",
        f"inferred_objective: {packet.inferred_objective}",
    ]
    sections.append("## repo surface\n" + "\n".join(meta))

    if packet.status_summary:
        sections.append("## status\n" + "\n".join(f"- {line}" for line in packet.status_summary))
    if packet.recent_commits:
        sections.append("## recent commits\n" + "\n".join(f"- {line}" for line in packet.recent_commits))
    if packet.diff_stats:
        sections.append("## diff stats\n" + packet.diff_stats)
    if packet.diff_excerpt:
        sections.append("## diff excerpt\n" + packet.diff_excerpt)

    if packet.docs:
        doc_chunks = []
        for doc in packet.docs:
            doc_chunks.append(f"### {doc.path}\n{doc.excerpt}")
        sections.append("## nearby docs\n" + "\n\n".join(doc_chunks))
    if packet.file_excerpts:
        file_chunks = []
        for file_excerpt in packet.file_excerpts:
            file_chunks.append(f"### {file_excerpt.path}\n{file_excerpt.excerpt}")
        sections.append("## file excerpts\n" + "\n\n".join(file_chunks))

    rendered = "\n\n".join(sections)
    return truncate_middle(rendered, char_budget)
