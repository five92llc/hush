"""The Update button: the same ./update.sh you would run over SSH, started from Settings.

Only for a server installed with git (see update.sh). The script fetches the latest version from the project's own repository
and restarts Hush through systemd, so the user running Hush needs passwordless ``sudo systemctl restart hush``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _git(*args: str, repo: Path = REPO) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60, check=True).stdout.strip()


def status(fetch: bool = True, repo: Path = REPO) -> dict:
    if not sys.platform.startswith("linux") or not (repo / "update.sh").is_file() or not (repo / ".git").exists():
        return {"possible": False}
    try:
        if fetch:
            _git("fetch", "-q", "origin", "main", repo=repo)
        behind = int(_git("rev-list", "--count", "HEAD..origin/main", repo=repo) or 0)
        return {"possible": True, "behind": behind, "current": _git("log", "-1", "--format=%h %s", repo=repo),
                "latest": _git("log", "-1", "--format=%h %s", "origin/main", repo=repo),
                "changes": _git("log", "--format=%s", "-8", "HEAD..origin/main", repo=repo).splitlines()}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"possible": True, "error": f"Could not check for updates: {str(exc)[:160]}"}


def start(log_file: Path, repo: Path = REPO) -> None:
    out = open(log_file, "wb")
    subprocess.Popen(["bash", str(repo / "update.sh")], cwd=repo, stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True)
