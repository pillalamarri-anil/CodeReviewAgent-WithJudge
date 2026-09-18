"""The ONLY module that talks to the GitHub API (PRD s8 -- "no API call outside this
class"). Mirrors the PRD's ``BitbucketClient`` surface, adapted to GitHub REST v3.

Read:  get_pull_request, get_diff, get_pr_commits, get_pr_comments, get_tree, get_file
Write: set_build_status, post_summary_comment, post_inline_comment
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

_UA = "review-agent/0.1"


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, owner: str, repo: str, token: Optional[str] = None,
                 api_url: str = "https://api.github.com"):
        if not owner or not repo:
            raise GitHubError("GitHubClient needs owner and repo (set GITHUB_REPOSITORY)")
        self.owner = owner
        self.repo = repo
        self.token = token
        self.api_url = api_url.rstrip("/")
        self._cache = {}

    @property
    def _base(self) -> str:
        return f"{self.api_url}/repos/{self.owner}/{self.repo}"

    # ---- transport ---------------------------------------------------
    def _request(self, method: str, url: str, *, accept="application/vnd.github+json",
                 body: Optional[dict] = None, raw: bool = False):
        cache_key = (method, url, accept)
        if method == "GET" and cache_key in self._cache:
            return self._cache[cache_key]

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", accept)
        req.add_header("User-Agent", _UA)
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")

        last: Optional[Exception] = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    payload = r.read()
                out = payload if raw else (json.loads(payload.decode("utf-8")) if payload else {})
                if method == "GET":
                    self._cache[cache_key] = out
                return out
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (403, 429, 502, 503) and attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                detail = e.read().decode("utf-8", "replace")[:400] if hasattr(e, "read") else ""
                raise GitHubError(f"{method} {url} -> HTTP {e.code}: {detail}") from e
            except urllib.error.URLError as e:
                last = e
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise GitHubError(f"{method} {url} failed: {e}") from e
        raise GitHubError(str(last))

    def _get(self, url, **kw):
        return self._request("GET", url, **kw)

    def _post(self, url, body):
        return self._request("POST", url, body=body)

    def _paged(self, url: str) -> List[dict]:
        acc, page = [], 1
        sep = "&" if "?" in url else "?"
        while True:
            batch = self._get(f"{url}{sep}per_page=100&page={page}")
            if not isinstance(batch, list):
                break
            acc.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return acc

    # ---- PRD BitbucketClient surface: read ------------------------
    def get_pull_request(self, pr_id) -> dict:
        return self._get(f"{self._base}/pulls/{pr_id}")

    def get_diff(self, pr_id) -> str:
        return self._get(f"{self._base}/pulls/{pr_id}",
                         accept="application/vnd.github.v3.diff", raw=True).decode("utf-8", "replace")

    def get_pr_commits(self, pr_id) -> List[str]:
        return [c["commit"]["message"] for c in self._paged(f"{self._base}/pulls/{pr_id}/commits")]

    def get_pr_comments(self, pr_id) -> dict:
        return {
            "review": self._paged(f"{self._base}/pulls/{pr_id}/comments"),
            "issue": self._paged(f"{self._base}/issues/{pr_id}/comments"),
        }

    def get_tree(self, ref) -> List[str]:
        data = self._get(f"{self._base}/git/trees/{urllib.parse.quote(str(ref))}?recursive=1")
        return [t["path"] for t in data.get("tree", []) if t.get("type") == "blob"]

    def get_file(self, path, ref) -> Optional[str]:
        try:
            data = self._get(
                f"{self._base}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(str(ref))}")
        except GitHubError as e:
            if "HTTP 404" in str(e):
                return None
            raise
        if isinstance(data, list) or data.get("encoding") != "base64":
            return None
        return base64.b64decode(data["content"]).decode("utf-8", "replace")

    # ---- PRD BitbucketClient surface: write ----------------------
    def set_build_status(self, commit_sha: str, state: str, target_url: str = "",
                         context: str = "ai-review", description: str = "") -> dict:
        """state: pending | success | failure | error"""
        body = {"state": state, "context": context}
        if target_url:
            body["target_url"] = target_url
        if description:
            body["description"] = description[:140]
        return self._post(f"{self._base}/statuses/{commit_sha}", body)

    def post_summary_comment(self, pr_id, body: str) -> dict:
        return self._post(f"{self._base}/issues/{pr_id}/comments", {"body": body})

    def post_inline_comment(self, pr_id, commit_sha: str, path: str, line: int, body: str) -> dict:
        return self._post(
            f"{self._base}/pulls/{pr_id}/comments",
            {"body": body, "commit_id": commit_sha, "path": path, "line": line, "side": "RIGHT"},
        )
