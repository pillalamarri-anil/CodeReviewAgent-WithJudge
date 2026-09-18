"""Local git helpers -- the fallback diff source when there is no PR API access
(PRD s4 step 2: "fallback `git diff base...head` on a clean checkout")."""

from __future__ import annotations

import subprocess
from typing import List, Optional


class GitError(RuntimeError):
    pass


def _git(repo: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _resolvable(repo: str, ref: str) -> Optional[str]:
    for candidate in (ref, f"origin/{ref}"):
        try:
            return _git(repo, "rev-parse", "--verify", "--quiet", candidate).strip() or None
        except GitError:
            continue
    return None


def resolve_sha(repo: str, ref: str) -> str:
    sha = _resolvable(repo, ref)
    if not sha:
        raise GitError(f"cannot resolve ref {ref!r} in {repo}")
    return sha


def unified_diff(repo: str, base: str, head: str) -> str:
    """`git diff <base>...<head>` (merge-base three-dot form, like a PR diff)."""
    base_ref = _pick_ref(repo, base)
    head_ref = _pick_ref(repo, head)
    return _git(repo, "diff", "--no-color", f"{base_ref}...{head_ref}")


def _pick_ref(repo: str, ref: str) -> str:
    for candidate in (ref, f"origin/{ref}"):
        try:
            _git(repo, "rev-parse", "--verify", "--quiet", candidate)
            return candidate
        except GitError:
            continue
    return ref


def commit_messages(repo: str, base: str, head: str) -> List[str]:
    try:
        out = _git(repo, "log", "--format=%s", f"{_pick_ref(repo, base)}..{_pick_ref(repo, head)}")
    except GitError:
        return []
    return [line for line in out.splitlines() if line.strip()]


def current_sha(repo: str) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()
