"""GitHub REST API client — repos, files, issues."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("jarvis.integrations.github")

_BASE_URL = "https://api.github.com"


class GitHubClient:
    """Async client for the GitHub REST API."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token or settings.GITHUB_TOKEN

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def search_repos(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Search GitHub repositories."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/search/repositories",
                headers=self._headers(),
                params={"q": query, "per_page": max_results, "sort": "stars"},
            )
            resp.raise_for_status()
            data = resp.json()

        return [
            {
                "full_name": r["full_name"],
                "description": r.get("description", ""),
                "stars": r.get("stargazers_count", 0),
                "language": r.get("language", ""),
                "url": r.get("html_url", ""),
            }
            for r in data.get("items", [])[:max_results]
        ]

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Get repository information."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/repos/{owner}/{repo}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "full_name": data["full_name"],
            "description": data.get("description", ""),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "language": data.get("language", ""),
            "default_branch": data.get("default_branch", "main"),
            "url": data.get("html_url", ""),
        }

    async def read_file(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
    ) -> dict[str, Any]:
        """Read a file from a repository."""
        params: dict[str, str] = {}
        if ref:
            params["ref"] = ref

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/repos/{owner}/{repo}/contents/{path}",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        content = ""
        if data.get("encoding") == "base64" and data.get("content"):
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")

        return {
            "name": data.get("name", ""),
            "path": data.get("path", path),
            "size": data.get("size", 0),
            "content": content[:10000],
            "url": data.get("html_url", ""),
        }

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """List issues for a repository."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/repos/{owner}/{repo}/issues",
                headers=self._headers(),
                params={"state": state, "per_page": max_results},
            )
            resp.raise_for_status()
            data = resp.json()

        return [
            {
                "number": issue["number"],
                "title": issue.get("title", ""),
                "state": issue.get("state", ""),
                "user": issue.get("user", {}).get("login", ""),
                "labels": [l["name"] for l in issue.get("labels", [])],
                "created_at": issue.get("created_at", ""),
                "url": issue.get("html_url", ""),
            }
            for issue in data
            if not issue.get("pull_request")  # Exclude PRs
        ]

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new issue."""
        if not self._token:
            return {"error": "GitHub token not configured (GITHUB_TOKEN missing)."}

        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_BASE_URL}/repos/{owner}/{repo}/issues",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "number": data["number"],
            "title": data["title"],
            "url": data["html_url"],
        }
