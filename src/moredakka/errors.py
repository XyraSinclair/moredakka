from __future__ import annotations


class MoreDakkaRuntimeError(RuntimeError):
    def __init__(self, message: str, *, run_artifact_path: str | None = None) -> None:
        super().__init__(message)
        self.run_artifact_path = run_artifact_path
