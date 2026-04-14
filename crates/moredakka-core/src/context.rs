use crate::config::AppConfig;
use crate::util::{run_command, safe_read_text, truncate_middle};
use serde::Serialize;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug, Serialize)]
pub struct DocSnippet {
    pub path: String,
    pub excerpt: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct FileExcerpt {
    pub path: String,
    pub excerpt: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ContextPacket {
    pub cwd: String,
    pub repo_root: Option<String>,
    pub mode: String,
    pub objective: String,
    pub inferred_objective: String,
    pub base_ref: String,
    pub branch: Option<String>,
    pub status_summary: Vec<String>,
    pub changed_files: Vec<String>,
    pub diff_stats: String,
    pub diff_excerpt: String,
    pub recent_commits: Vec<String>,
    pub docs: Vec<DocSnippet>,
    pub file_excerpts: Vec<FileExcerpt>,
}

const DOC_CANDIDATES: &[&str] = &[
    "README.md",
    "AGENTS.md",
    "PLAN.md",
    "TODO.md",
    "SPEC.md",
    "DESIGN.md",
];

fn git(cwd: &Path, args: &[&str]) -> Option<String> {
    run_command(cwd, "git", args)
}

fn find_repo_root(cwd: &Path) -> Option<PathBuf> {
    git(cwd, &["rev-parse", "--show-toplevel"]).map(PathBuf::from)
}

fn parse_status(output: &str) -> Vec<String> {
    output
        .lines()
        .filter_map(|raw| {
            let raw = raw.trim_end();
            if raw.is_empty() {
                return None;
            }
            let code = raw.get(0..2).unwrap_or("??").trim();
            let path = raw.get(3..).unwrap_or(raw).trim();
            Some(format!(
                "{} {}",
                if code.is_empty() { "??" } else { code },
                path
            ))
        })
        .collect()
}

fn review_merge_base(cwd: &Path, base_ref: &str) -> anyhow::Result<String> {
    git(cwd, &["merge-base", "HEAD", base_ref]).ok_or_else(|| anyhow::anyhow!("Unable to compute review diff against base ref '{base_ref}'. Check that the ref exists locally."))
}

fn review_changed_files(cwd: &Path, base_ref: &str) -> anyhow::Result<Vec<String>> {
    let merge_base = review_merge_base(cwd, base_ref)?;
    let output = git(
        cwd,
        &["diff", "--name-only", &format!("{merge_base}..HEAD")],
    )
    .unwrap_or_default();
    Ok(output
        .lines()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(ToOwned::to_owned)
        .take(12)
        .collect())
}

fn working_changed_files(root: &Path, status_summary: &[String]) -> Vec<String> {
    let mut files = Vec::new();
    for line in status_summary {
        let Some((_, path)) = line.split_once(' ') else {
            continue;
        };
        let candidate = root.join(path);
        if candidate.is_dir() {
            if let Ok(iter) = candidate.read_dir() {
                for entry in iter.flatten() {
                    if entry.path().is_file() {
                        if let Ok(rel) = entry.path().strip_prefix(root) {
                            files.push(rel.to_string_lossy().to_string());
                        }
                    }
                }
            }
        } else {
            files.push(path.to_string());
        }
        if files.len() >= 12 {
            break;
        }
    }
    files.truncate(12);
    files
}

fn collect_docs(cwd: &Path, repo_root: Option<&Path>) -> Vec<PathBuf> {
    let mut docs = Vec::new();
    let mut current = Some(cwd.to_path_buf());
    let stop = repo_root.unwrap_or(cwd).to_path_buf();
    while let Some(dir) = current {
        for name in DOC_CANDIDATES {
            let candidate = dir.join(name);
            if candidate.exists() && !docs.contains(&candidate) {
                docs.push(candidate);
                if docs.len() >= 6 {
                    return docs;
                }
            }
        }
        if dir == stop {
            break;
        }
        current = dir.parent().map(|p| p.to_path_buf());
    }
    docs
}

fn infer_objective(
    explicit: Option<&str>,
    branch: Option<&str>,
    changed_files: &[String],
) -> String {
    if let Some(v) = explicit {
        if !v.is_empty() {
            return v.to_string();
        }
    }
    if !changed_files.is_empty() {
        return format!(
            "Advance the current working changes in {}",
            changed_files
                .iter()
                .take(4)
                .cloned()
                .collect::<Vec<_>>()
                .join(", ")
        );
    }
    if let Some(branch) = branch {
        if branch != "main" && branch != "master" {
            return format!("Figure out the best next move for branch {branch}");
        }
    }
    "Figure out the best next move in the current working directory".into()
}

pub fn build_context_packet(
    cwd: &Path,
    mode: &str,
    objective: Option<&str>,
    base_ref: &str,
    char_budget: usize,
    _config: &AppConfig,
) -> anyhow::Result<ContextPacket> {
    let repo_root = find_repo_root(cwd);
    let branch = repo_root
        .as_ref()
        .and_then(|_| git(cwd, &["branch", "--show-current"]));
    let status_output = repo_root
        .as_ref()
        .and_then(|_| git(cwd, &["status", "--porcelain=v1"]))
        .unwrap_or_default();
    let status_summary = parse_status(&status_output);
    let changed_files = if repo_root.is_some() && mode == "review" {
        review_changed_files(cwd, base_ref)?
    } else {
        working_changed_files(repo_root.as_deref().unwrap_or(cwd), &status_summary)
    };
    let (diff_stats, diff_excerpt) = if repo_root.is_some() && mode == "review" {
        let merge_base = review_merge_base(cwd, base_ref)?;
        (
            git(cwd, &["diff", "--stat", &format!("{merge_base}..HEAD")]).unwrap_or_default(),
            git(
                cwd,
                &["diff", "--unified=3", &format!("{merge_base}..HEAD")],
            )
            .unwrap_or_default(),
        )
    } else {
        let staged = git(cwd, &["diff", "--stat", "--cached"]).unwrap_or_default();
        let unstaged = git(cwd, &["diff", "--stat"]).unwrap_or_default();
        let excerpt = [
            git(cwd, &["diff", "--cached", "--unified=3", "--no-ext-diff"])
                .map(|v| format!("## staged diff\n{v}")),
            git(cwd, &["diff", "--unified=3", "--no-ext-diff"])
                .map(|v| format!("## unstaged diff\n{v}")),
        ]
        .into_iter()
        .flatten()
        .collect::<Vec<_>>()
        .join("\n\n");
        (
            [staged, unstaged]
                .into_iter()
                .filter(|s| !s.is_empty())
                .collect::<Vec<_>>()
                .join("\n"),
            excerpt,
        )
    };
    let recent_commits = repo_root
        .as_ref()
        .and_then(|_| {
            git(
                cwd,
                &[
                    "log",
                    "--max-count=8",
                    "--date=short",
                    "--pretty=format:%h %ad %s",
                ],
            )
        })
        .unwrap_or_default()
        .lines()
        .map(ToOwned::to_owned)
        .collect();
    let docs = collect_docs(cwd, repo_root.as_deref())
        .into_iter()
        .filter_map(|path| {
            safe_read_text(&path, 2_000).map(|excerpt| DocSnippet {
                path: path
                    .strip_prefix(repo_root.as_deref().unwrap_or(cwd))
                    .unwrap_or(&path)
                    .to_string_lossy()
                    .to_string(),
                excerpt,
            })
        })
        .collect();
    let file_excerpts = changed_files
        .iter()
        .take(6)
        .filter_map(|rel| {
            let path = repo_root.as_deref().unwrap_or(cwd).join(rel);
            safe_read_text(&path, 1_200).map(|excerpt| FileExcerpt {
                path: rel.clone(),
                excerpt,
            })
        })
        .collect();
    let inferred_objective = infer_objective(objective, branch.as_deref(), &changed_files);
    Ok(ContextPacket {
        cwd: cwd.display().to_string(),
        repo_root: repo_root.as_ref().map(|p| p.display().to_string()),
        mode: mode.to_string(),
        objective: objective.unwrap_or_default().to_string(),
        inferred_objective,
        base_ref: base_ref.to_string(),
        branch,
        status_summary,
        changed_files,
        diff_stats,
        diff_excerpt: truncate_middle(
            &diff_excerpt,
            std::cmp::max(3000, (char_budget as f64 * 0.45) as usize),
        ),
        recent_commits,
        docs,
        file_excerpts,
    })
}
