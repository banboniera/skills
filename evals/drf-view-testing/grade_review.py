"""Grade one review run: does the report find each weakness planted in review_tests.py, without changing the tests?
Usage: python grade_review.py <run-dir> <workspace> <python>
"""

import json
import re
import sys
from pathlib import Path

# (finding, patterns that must all appear in one paragraph, list item, or table row; a test name also matches a test_views.py:LINE citation)
FINDINGS = [
    ("anonymous test accepts 401 or 403", ["test_list_requires_login", r"(?i)401|either|assertIn|accepts both|both statuses"]),
    ("list test asserts only a non-empty result", ["test_list_returns_tickets", r"(?i)only (checks|asserts)|non-empty|truthy|any row|exact|archived|order|which ticket|ids"]),
    ("scoping tested only on the list", [r"(?i)(detail|retrieve|close|assign|update|delete|destroy|custom action)[^|\n]{0,150}(other[- ]company|another company|other compan|cross-company|scop|tenant|404)|(other[- ]company|another company|other compan|cross-company|scop|tenant)[^|\n]{0,150}(detail|retrieve|close|assign|update|delete|destroy)"]),
    ("status filter test matches every row", ["test_status_filter", r"(?i)every|all (rows|tickets|seeded|open)|both|discriminat|closed|non-matching"]),
    ("query count measured on one row", ["test_list_query_count", r"(?i)one (row|ticket)|single|1 row|too few|N\+1|assignee|grow|more rows"]),
    ("create test ignores stored state", ["test_create_ticket", r"(?i)company|created_by|stored|persist|database|\bDB\b|refresh"]),
    ("delete test ignores the archive", ["test_admin_can_delete_ticket", r"(?i)archiv|still exists|\brow\b|\bDB\b|database|refresh|soft"]),
    ("delete denial for other roles untested", ["test_admin_can_delete_ticket", r"(?i)agent|viewer|other roles?|denied|403|forbidden"]),
    ("close test skips notification and closed_at", ["test_close_ticket", r"(?i)notif|on_commit|captureOnCommitCallbacks|closed_at|mock|patch"]),
    ("agent assign test asserts the bug", ["test_agent_can_assign", r"(?i)bug|admin|docstring|promise|should be 403|403|forbidden"]),
    ("stats test has no rows it must leave out", ["test_stats", r"(?i)other[- ]compan|another company|archived|scop|cross|tenant"]),
    ("viewer role never tested", [r"(?i)viewer"]),
    ("archived list untested", [r"(?i)archived=true|\?archived|`archived`|archived (list|param|filter|view|query|tickets list)"]),
]


def test_ranges(source: str) -> dict[str, range]:
    """Line range of each test function, so a finding may cite test_views.py:LINE instead of the test's name."""
    starts = [(m.group(1), source[: m.start()].count("\n") + 1) for m in re.finditer(r"^    (?:@.*\n    )?def (test_\w+)", source, re.M)]
    ends = [line - 1 for _, line in starts[1:]] + [source.count("\n") + 1]
    return {name: range(start, end + 1) for (name, start), end in zip(starts, ends)}


def cites(chunk: str, name: str, ranges: dict[str, range]) -> bool:
    if name in chunk:
        return True
    for a, b in re.findall(r"test_views\.py:(\d+)(?:[-–](\d+))?", chunk):
        if set(range(int(a), int(b or a) + 1)) & set(ranges[name]):
            return True
    return False


def main(run_dir: Path, ws: Path) -> None:
    report = (run_dir / "report.md").read_text() if (run_dir / "report.md").exists() else ""
    # A finding may be one paragraph, list item, or table row, or a whole section under a heading.
    chunks = [c for c in re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.|\|)\s)", report) if c.strip()]
    chunks += [c for c in re.split(r"\n(?=#{1,4} )", report) if c.strip()]
    original = (Path(__file__).parent / "review_tests.py").read_text()
    ranges = test_ranges(original)

    def hit(chunk: str, pats: list[str]) -> bool:
        return all(cites(chunk, p, ranges) if p in ranges else re.search(p, chunk) for p in pats)

    found = {name: any(hit(c, pats) for c in chunks) for name, pats in FINDINGS}
    unchanged = (ws / "tickets" / "tests" / "views" / "test_views.py").read_text() == original
    result = {"found": sum(found.values()), "total": len(FINDINGS), "findings": found, "tests_unchanged": unchanged}
    (run_dir / "grading.json").write_text(json.dumps(result, indent=2))
    print(f"findings {sum(found.values())}/{len(FINDINGS)}; tests unchanged: {unchanged}")
    for name, ok in found.items():
        if not ok:
            print(f"  missed: {name}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
