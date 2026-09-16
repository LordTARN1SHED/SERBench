"""Security and refresh regression tests for the public aggregate index."""

from datetime import datetime, timezone
import hashlib
import json
import unittest

from tools import update_leaderboard as board


class MemoryPath:
    """Exercise atomic replacement without relying on host temp permissions."""

    def __init__(self, files: dict[str, str], name: str) -> None:
        self.files = files
        self.name = name

    def read_text(self, **_kwargs) -> str:
        try:
            return self.files[self.name]
        except KeyError as exc:
            raise FileNotFoundError(self.name) from exc

    def write_text(self, value: str, **_kwargs) -> None:
        self.files[self.name] = value

    def with_name(self, name: str) -> "MemoryPath":
        return MemoryPath(self.files, name)

    def replace(self, target: "MemoryPath") -> None:
        self.files[target.name] = self.files.pop(self.name)

    def unlink(self, missing_ok: bool = False) -> None:
        if not missing_ok or self.name in self.files:
            del self.files[self.name]


def form(method: str = "Safe Method", consent: str = board.CONSENT, release: str = board.RELEASE) -> str:
    values = (
        method,
        "https://raw.githubusercontent.com/submitter/example/" + "a" * 40 + "/predictions.jsonl",
        "b" * 64,
        release,
        "A public description.",
        consent,
    )
    return "\n\n".join(f"### {field}\n\n{value}" for field, value in zip(board.FIELDS, values))


def issue(number: int = 12, body: str | None = None) -> dict:
    return {
        "number": number,
        "title": "[Evaluation] Safe Method",
        "labels": [{"name": "evaluation"}],
        "body": form() if body is None else body,
    }


def comment(number: int = 12, body: str | None = None, actor_id: int = board.OWNER_ACTOR_ID) -> dict:
    original = form() if body is None else body
    sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
    lines = [
        f"<!-- SERBENCH-EVAL:v1 issue={number} body_sha256={sha} result=accepted -->",
        "SERBench Test500 aggregate result (500 states):",
        "",
        "- Complete-MSS@5: 12.34%",
        "- Complete-MSS@8: 56.78%",
        "- Group@5: 90.00%",
        "- Group@8: 100.00%",
        "- Necessity@5: 0.00%",
    ]
    return {
        "id": 12345,
        "user": {"id": actor_id, "login": board.OWNER},
        "issue_url": f"{board.API_BASE}/issues/{number}",
        "created_at": "2026-09-16T11:22:33Z",
        "body": "\n".join(lines),
    }


class LeaderboardTests(unittest.TestCase):
    def test_valid_result_has_exact_public_schema_and_provenance(self) -> None:
        rows = board.build_results([comment()], lambda _number: issue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "method": "Safe Method",
                "issue_url": "https://github.com/LordTARN1SHED/SERBench/issues/12",
                "comment_url": "https://github.com/LordTARN1SHED/SERBench/issues/12#issuecomment-12345",
                "evaluated_at": "2026-09-16T11:22:33Z",
                "metrics": {
                    "mss_complete@5": 12.34,
                    "mss_complete@8": 56.78,
                    "group_recall@5": 90.0,
                    "group_recall@8": 100.0,
                    "necessity_weighted_recall@5": 0.0,
                },
            },
        )

    def test_five_zero_percentages_are_valid(self) -> None:
        zero = comment()
        for old in ("12.34%", "56.78%", "90.00%", "100.00%"):
            zero["body"] = zero["body"].replace(old, "0.00%")
        rows = board.build_results([zero], lambda _number: issue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]["metrics"]), {key for key, _label in board.METRICS})
        self.assertTrue(all(value == 0.0 for value in rows[0]["metrics"].values()))

    def test_spoofed_login_with_other_numeric_actor_is_ignored(self) -> None:
        forged = comment(actor_id=42)
        self.assertEqual(board.build_results([forged], lambda _number: issue()), [])
        forged["user"]["id"] = True  # bool must not pass as integer 1.
        self.assertEqual(board.build_results([forged], lambda _number: issue()), [])

    def test_malformed_or_extra_metrics_are_ignored(self) -> None:
        valid = comment()
        for bad_line in (
            "- Group@5: NaN%",
            "- Group@5: 100.01%",
            "- Group@5: -1.00%",
            "- Group@5: 90%",
            "- Unknown: 90.00%",
        ):
            with self.subTest(bad_line=bad_line):
                altered = dict(valid, body=valid["body"].replace("- Group@5: 90.00%", bad_line))
                self.assertEqual(board.build_results([altered], lambda _number: issue()), [])
        extra = dict(valid, body=valid["body"] + "\n- Another metric: 1.00%")
        self.assertEqual(board.build_results([extra], lambda _number: issue()), [])

    def test_missing_consent_and_wrong_release_are_ignored(self) -> None:
        for body in (
            form(consent="_No response_"),
            form(consent="I do not consent."),
            form(release="unfrozen-release"),
        ):
            with self.subTest(body=body[-80:]):
                self.assertEqual(board.build_results([comment(body=body)], lambda _number: issue(body=body)), [])

    def test_edited_issue_body_revokes_matching_old_comment(self) -> None:
        self.assertEqual(
            board.build_results([comment()], lambda _number: issue(body=form(method="Another Method"))), []
        )
        changed_hash = comment()
        changed_hash["body"] = changed_hash["body"].replace("body_sha256=", "body_sha256=" + "0")
        self.assertEqual(board.build_results([changed_hash], lambda _number: issue()), [])

    def test_issue_metadata_and_comment_provenance_must_match(self) -> None:
        valid = comment()
        wrong_issue_url = dict(valid, issue_url="https://attacker.example/issues/12")
        self.assertEqual(board.build_results([wrong_issue_url], lambda _number: issue()), [])
        wrong_id = dict(valid, id="12345")
        self.assertEqual(board.build_results([wrong_id], lambda _number: issue()), [])
        for altered_issue in (
            dict(issue(), labels=[]),
            dict(issue(), title="An unrelated issue"),
            dict(issue(), pull_request={"url": "https://example.invalid"}),
            dict(issue(), number=13),
        ):
            with self.subTest(altered_issue=altered_issue):
                self.assertEqual(board.build_results([valid], lambda _number: altered_issue), [])

    def test_duplicate_owner_comments_and_edited_comment_are_ignored(self) -> None:
        first = comment()
        second = dict(first, id=12346)
        self.assertEqual(board.build_results([first, second], lambda _number: issue()), [])
        edited = dict(first, body=first["body"].replace("result=accepted", "result=rejected"))
        self.assertEqual(board.build_results([edited], lambda _number: issue()), [])

    def test_deletion_refresh_and_idempotent_timestamp(self) -> None:
        files: dict[str, str] = {}
        path = MemoryPath(files, "community_results.json")
        initial = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
        rows = board.build_results([comment()], lambda _number: issue())
        self.assertTrue(board.write_if_changed(path, rows, initial))
        before = path.read_text()
        self.assertFalse(board.write_if_changed(path, rows, datetime(2026, 9, 16, 13, tzinfo=timezone.utc)))
        self.assertEqual(path.read_text(), before)
        self.assertTrue(board.write_if_changed(path, [], datetime(2026, 9, 16, 14, tzinfo=timezone.utc)))
        self.assertEqual(json.loads(path.read_text())["results"], [])
        self.assertEqual(json.loads(path.read_text())["updated_at"], "2026-09-16T14:00:00Z")
        files[path.name] = '{"schema_version": true, "updated_at": "2026-09-16T14:00:00Z", "results": []}'
        self.assertTrue(board.write_if_changed(path, [], datetime(2026, 9, 16, 15, tzinfo=timezone.utc)))
        self.assertEqual(json.loads(path.read_text())["schema_version"], 1)

    def test_api_pagination_and_invalid_page_fail_closed(self) -> None:
        api = board.GitHubAPI.__new__(board.GitHubAPI)
        pages = {1: [{"id": i} for i in range(100)], 2: [{"id": 101}]}
        api.get = lambda path: pages[int(path.rsplit("page=", 1)[1])]
        self.assertEqual(len(api.all_comments()), 101)
        api.get = lambda _path: {"error": "rate limited"}
        with self.assertRaises(ValueError):
            api.all_comments()


if __name__ == "__main__":
    unittest.main()
