"""Rebuild the public leaderboard from authenticated evaluation comments.

Only GitHub's issue/comment API is read. This module never fetches predictions,
imports the private evaluator, or executes content supplied by submitters.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib.request import HTTPRedirectHandler, Request, build_opener


OWNER = "LordTARN1SHED"
REPO = "SERBench"
OWNER_ACTOR_ID = 134487451
API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"
ISSUE_API = re.compile(rf"\A{re.escape(API_BASE)}/issues/([1-9][0-9]*)\Z")
RELEASE = "serbench-public-v1-v5.6"
CONSENT = "I agree to publish my predictions, method name, and aggregate scores."
FIELDS = (
    "Method name",
    "Prediction URL",
    "Prediction SHA256",
    "Dataset release",
    "Method description",
    "Publication consent",
)
METRICS = (
    ("mss_complete@5", "Complete-MSS@5"),
    ("mss_complete@8", "Complete-MSS@8"),
    ("group_recall@5", "Group@5"),
    ("group_recall@8", "Group@8"),
    ("necessity_weighted_recall@5", "Necessity@5"),
)
HEADING = re.compile(r"^### ([^\r\n]+)$", re.MULTILINE)
METHOD = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._ +\-]{0,63}\Z")
MARKER = re.compile(
    r"\A<!-- SERBENCH-EVAL:v1 issue=([1-9][0-9]*) "
    r"body_sha256=([0-9a-f]{64}) result=accepted -->\Z"
)
API_PAGE_LIMIT = 1000  # Fail closed instead of publishing a truncated rebuild.
OUTPUT = Path(__file__).resolve().parents[1] / "community_results.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class GitHubAPI:
    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN is required")
        self.token = token
        self.opener = build_opener(NoRedirect())

    def get(self, path: str) -> Any:
        # All paths are constructed locally; no event or comment value becomes a URL.
        if not re.fullmatch(r"/[A-Za-z0-9_/?=&-]+", path):
            raise ValueError("invalid API path")
        request = Request(
            API_BASE + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "serbench-public-leaderboard/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with self.opener.open(request, timeout=20) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("GitHub API response too large")
        return json.loads(data)

    def all_comments(self) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        for page in range(1, API_PAGE_LIMIT + 1):
            rows = self.get(f"/issues/comments?sort=created&direction=asc&per_page=100&page={page}")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("invalid GitHub comments response")
            comments.extend(rows)
            if len(rows) < 100:
                return comments
        raise ValueError("GitHub comment pagination limit reached")

    def issue(self, number: int) -> dict[str, Any]:
        row = self.get(f"/issues/{number}")
        if not isinstance(row, dict) or type(row.get("number")) is not int or row["number"] != number:
            raise ValueError("invalid GitHub issue response")
        return row


def iso_utc(value: str) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z", value
    ):
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant.isoformat().replace("+00:00", "Z")


def issue_method(body: Any) -> str | None:
    """Mirror the private form's exact headings and publication checks."""
    if not isinstance(body, str) or len(body) > 12_000:
        return None
    matches = list(HEADING.finditer(body))
    if [match.group(1) for match in matches] != list(FIELDS):
        return None
    if body[: matches[0].start()].strip():
        return None
    values = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        value = body[match.end() : end].strip()
        if not value or value == "_No response_":
            return None
        values.append(value)
    method, _url, checksum, release, description, consent = values
    if not METHOD.fullmatch(method) or len(description) > 2_000:
        return None
    if not re.fullmatch(r"[0-9a-fA-F]{64}", checksum):
        return None
    if release != RELEASE or consent != CONSENT:
        return None
    return method


def accepted_comment(comment: dict[str, Any], number: int) -> tuple[str, dict[str, float], str] | None:
    body = comment.get("body")
    if not isinstance(body, str):
        return None
    lines = body.split("\n")
    if len(lines) != 8 or lines[1:3] != ["SERBench Test500 aggregate result (500 states):", ""]:
        return None
    marker = MARKER.fullmatch(lines[0])
    if marker is None or int(marker.group(1)) != number:
        return None
    metric_values: dict[str, float] = {}
    for line, (key, label) in zip(lines[3:], METRICS):
        match = re.fullmatch(rf"- {re.escape(label)}: ([0-9]{{1,3}}\.[0-9]{{2}})%", line)
        if match is None:
            return None
        value = float(match.group(1))
        if not 0 <= value <= 100:
            return None
        metric_values[key] = value
    evaluated_at = iso_utc(comment.get("created_at"))
    if evaluated_at is None:
        return None
    return marker.group(2), metric_values, evaluated_at


def build_results(
    comments: list[dict[str, Any]], issue_fetch: Callable[[int], dict[str, Any]]
) -> list[dict[str, Any]]:
    by_issue: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for comment in comments:
        actor = comment.get("user")
        if not isinstance(actor, dict) or type(actor.get("id")) is not int or actor["id"] != OWNER_ACTOR_ID:
            continue
        body = comment.get("body")
        if not isinstance(body, str) or "SERBENCH-EVAL:" not in body:
            continue
        issue_url = comment.get("issue_url")
        match = ISSUE_API.fullmatch(issue_url) if isinstance(issue_url, str) else None
        if match is not None:
            by_issue[int(match.group(1))].append(comment)

    results = []
    for number, candidates in by_issue.items():
        # An ambiguous owner-authored evaluation is not silently selected.
        if len(candidates) != 1:
            continue
        parsed = accepted_comment(candidates[0], number)
        if parsed is None:
            continue  # Rejected or edited/malformed result.
        body_hash, metrics, evaluated_at = parsed
        issue = issue_fetch(number)
        labels = issue.get("labels")
        if (
            type(issue.get("number")) is not int or issue["number"] != number
            or "pull_request" in issue
            or not isinstance(issue.get("title"), str)
            or not re.match(r"\A\[Evaluation\](?:\s|$)", issue["title"])
            or not isinstance(labels, list)
            or not any(isinstance(label, dict) and label.get("name") == "evaluation" for label in labels)
        ):
            continue
        body = issue.get("body")
        method = issue_method(body)
        if method is None or hashlib.sha256(body.encode("utf-8")).hexdigest() != body_hash:
            continue
        comment_id = candidates[0].get("id")
        if type(comment_id) is not int or comment_id <= 0:
            continue
        issue_url = f"https://github.com/{OWNER}/{REPO}/issues/{number}"
        results.append(
            {
                "method": method,
                "issue_url": issue_url,
                "comment_url": f"{issue_url}#issuecomment-{comment_id}",
                "evaluated_at": evaluated_at,
                "metrics": metrics,
            }
        )
    return sorted(results, key=lambda row: (row["evaluated_at"], row["issue_url"], row["comment_url"]))


def write_if_changed(path: Path, results: list[dict[str, Any]], now: datetime | None = None) -> bool:
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = None
    if (
        isinstance(existing, dict) and set(existing) == {"schema_version", "updated_at", "results"}
        and type(existing["schema_version"]) is int and existing["schema_version"] == 1
        and iso_utc(existing.get("updated_at")) is not None
        and existing.get("results") == results
    ):
        return False
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    output = {"schema_version": 1, "updated_at": timestamp, "results": results}
    data = json.dumps(output, ensure_ascii=True, indent=2) + "\n"
    # The old public file remains intact if collection or validation fails.
    temp = path.with_name(path.name + ".tmp")
    try:
        temp.write_text(data, encoding="utf-8", newline="\n")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return True


def main() -> int:
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REPOSITORY") != f"{OWNER}/{REPO}":
            raise ValueError("must run in the public repository Actions workflow")
        client = GitHubAPI(os.environ.get("GITHUB_TOKEN", ""))
        results = build_results(client.all_comments(), client.issue)
        changed = write_if_changed(OUTPUT, results)
        print(f"public leaderboard: {len(results)} entries; {'changed' if changed else 'unchanged'}")
        return 0
    except Exception:
        # API responses and user-controlled text must not appear in workflow logs.
        print("public leaderboard rebuild failed; previous file retained", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
