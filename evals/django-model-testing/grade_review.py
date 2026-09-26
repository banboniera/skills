"""Grade one review run: does the report find each weakness planted in review_tests.py, without changing the tests?
Usage: python grade_review.py <run-dir> <workspace> <python>
"""

import json
import re
import sys
from pathlib import Path

# (finding, patterns that must all appear in one paragraph, list item, or table row; a test name also matches a test_models.py:LINE citation)
FINDINGS = [
    ("plate test input already uppercase", ["test_plate_is_uppercase", r"(?i)already|lowercase|discriminat|no-op|doesn.t exercise|does not exercise|never exercise"]),
    ("IntegrityError outside atomic()", ["test_duplicate_plate_is_rejected", r"atomic"]),
    ("zero-balance test never runs the validator", ["test_zero_balance_is_allowed", r"(?i)full_clean|validator|objects\.create|create\(\)"]),
    ("closed_at test passes for the wrong error", ["test_closed_order_requires_closed_at", r"(?i)message_dict|pin|wrong|vehicle|other workshop|another workshop|any ValidationError"]),
    ("open() test asserts the bug", ["test_open_excludes_ready_and_closed_orders", r"(?i)docstring|promise|contract|open_order_count|bug|restat|implementation"]),
    ("for_workshop() test checks inclusion only", ["test_for_workshop_returns_its_orders", r"(?i)exclu|other workshop|another workshop|leave out|leaves out|inclusion"]),
    ("notification test never runs on_commit callbacks", ["test_saving_ready_twice_notifies_once", r"(?i)on_commit|captureOnCommitCallbacks|callbacks"]),
    ("soft-delete test only checks the row exists", ["test_deleting_vehicle_with_orders_keeps_it", r"(?i)is_deleted|deleted_at|alive"]),
    ("queryset delete path untested", [r"(?i)QuerySet\.delete|queryset\.delete|queryset delete|bulk delete|\.filter\([^)]*\)\.delete|VehicleQuerySet\.delete"]),
    ("partial save untested", [r"update_fields"]),
    ("conditional constraint's allowed side untested", [r"(?i)condition|is_deleted=False|soft-deleted (duplicate|vehicle)|deleted vehicle|live vehicles"]),
    ("negative balance never tested", [r"(?i)negative|-0\.01|boundary"]),
]


def test_ranges(source: str) -> dict[str, range]:
    """Line range of each test function, so a finding may cite test_models.py:LINE instead of the test's name."""
    starts = [(m.group(1), source[: m.start()].count("\n") + 1) for m in re.finditer(r"^    (?:@.*\n    )?def (test_\w+)", source, re.M)]
    ends = [line - 1 for _, line in starts[1:]] + [source.count("\n") + 1]
    return {name: range(start, end + 1) for (name, start), end in zip(starts, ends)}


def cites(chunk: str, name: str, ranges: dict[str, range]) -> bool:
    if name in chunk:
        return True
    for a, b in re.findall(r"test_models\.py:(\d+)(?:[-–](\d+))?", chunk):
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
    unchanged = (ws / "shop" / "tests" / "test_models.py").read_text() == original
    result = {"found": sum(found.values()), "total": len(FINDINGS), "findings": found, "tests_unchanged": unchanged}
    (run_dir / "grading.json").write_text(json.dumps(result, indent=2))
    print(f"findings {sum(found.values())}/{len(FINDINGS)}; tests unchanged: {unchanged}")
    for name, ok in found.items():
        if not ok:
            print(f"  missed: {name}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
