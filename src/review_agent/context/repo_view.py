"""Read-only view of the repo at PR head.

``LocalRepoView`` reads from a local checkout on disk (CI has one -- fast, no network).
``GitHubTreeRepoView`` reads from the GitHub git-tree at a ref (no checkout needed),
ported from ``context_creator.ipynb`` cell 8.

Both check an optional local ``overlay_dir`` first, so knowledge docs / rules the
sample repo does not ship yet can be supplied without a fork.
"""

from __future__ import annotations

import os
from typing import List, Optional

_SKIP_DIRS = {".git", "target", "build", "node_modules", ".idea", ".venv", "__pycache__"}


class LocalRepoView:
    def __init__(self, repo_path: str, overlay_dir: str = ""):
        self.repo_path = os.path.abspath(repo_path)
        self.overlay_dir = os.path.abspath(overlay_dir) if overlay_dir else ""
        self._files: Optional[List[str]] = None
        self._cache = {}

    def list_files(self) -> List[str]:
        if self._files is None:
            found = set()
            for base in (self.repo_path, self.overlay_dir):
                if not base or not os.path.isdir(base):
                    continue
                for root, dirs, files in os.walk(base):
                    dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
                    for fn in files:
                        rel = os.path.relpath(os.path.join(root, fn), base)
                        found.add(rel.replace(os.sep, "/"))
            self._files = sorted(found)
        return self._files

    def read(self, path: str) -> Optional[str]:
        if path in self._cache:
            return self._cache[path]
        content = None
        for base in (self.overlay_dir, self.repo_path):
            if not base:
                continue
            fp = os.path.join(base, path)
            if os.path.isfile(fp):
                with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                break
        self._cache[path] = content
        return content


class GitHubTreeRepoView:
    """No checkout: file contents come from the GitHub tree at ``head_ref``."""

    def __init__(self, client, head_ref: str, overlay_dir: str = ""):
        self.client = client
        self.head_ref = head_ref
        self.overlay_dir = overlay_dir
        self._files: Optional[List[str]] = None
        self._cache = {}

    def list_files(self) -> List[str]:
        if self._files is None:
            tree = set(self.client.get_tree(self.head_ref))
            if self.overlay_dir and os.path.isdir(self.overlay_dir):
                for root, _, files in os.walk(self.overlay_dir):
                    for fn in files:
                        rel = os.path.relpath(os.path.join(root, fn), self.overlay_dir)
                        tree.add(rel.replace(os.sep, "/"))
            self._files = sorted(tree)
        return self._files

    def read(self, path: str) -> Optional[str]:
        if path in self._cache:
            return self._cache[path]
        content = None
        if self.overlay_dir:
            fp = os.path.join(self.overlay_dir, path)
            if os.path.isfile(fp):
                with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
        if content is None:
            content = self.client.get_file(path, self.head_ref)
        self._cache[path] = content
        return content
