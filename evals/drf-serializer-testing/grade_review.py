"""Grade one review run: does the report find each weakness planted in review_tests.py, without changing the tests?
Usage: python grade_review.py <run-dir> <workspace> <python>
"""

import json
import re
import sys
from pathlib import Path

# (finding, patterns that must all appear in one paragraph, list item, or table row; a test name also matches a test_serializers.py:LINE citation)
FINDINGS = [
    ("placing test passes for the wrong reason", ["test_placing_without_lines_is_rejected", r"(?i)customer|wrong reason|never reach|never runs|field error|any error|errors\[.lines.\]|which error"]),
    ("duplicate SKU test passes on save()'s own assertion", ["test_duplicate_sku_is_rejected", r"(?i)AssertionError|is_valid|invalid data|wrong reason|any exception|assertRaises\(Exception|IntegrityError|serializer\.errors"]),
    ("SKU input already uppercase", ["test_sku_is_stored_uppercase", r"(?i)already|lowercase|discriminat|no-op|doesn.t exercise|does not exercise|never exercise|whitespace|trim"]),
    ("own-SKU update test asserts the bug", ["test_update_with_same_sku_is_rejected", r"(?i)bug|promise|docstring|should (be allowed|pass|succeed)|its own|exclude|self\.instance|inverted|backwards"]),
    ("output test checks a key subset", ["test_output", r"(?i)exact|subset|write.only|leak|extra keys|\bnote\b"]),
    ("total test has no discount or rounding", ["test_output", r"(?i)discount|round|half"]),
    ("query test pins the N+1", ["test_list_rows", r"(?i)prefetch|N\+1|zero queries|0 queries|assertNumQueries\(0\)|per.row|per order|per-order"]),
    ("discount boundaries untested", ["test_discount_limits", r"(?i)\b50\b|boundar|edge|negative|-0\.01|50\.01"]),
    ("create test asserts too little", ["test_create_order", r"(?i)company|created_by|unit.price|refresh_from_db|placed_at|quantit|only (checks|asserts|counts)"]),
    ("partial update keeping lines untested", [r"(?i)partial\w*[^|\n]{0,150}\blines?\b|\blines?\b[^|\n]{0,150}partial"]),
    ("line product scoping untested", [r"(?i)product", r"(?i)other[- ]company|another company|other tenant|cross-company|scop|tenant"]),
    ("line add/update/delete on update untested", [r"(?i)\b(add\w*|new)\b[^|\n]{0,40}\blines?\b|\blines?\b[^|\n]{0,20}\badd", r"(?i)(delet|remov)\w*[^|\n]{0,40}(lines?|missing|omitted)|(missing|omitted)[^|\n]{0,40}(delet|remov)"]),
]

def test_ranges(source: str) -> dict[str, range]:
    """Line range of each test function, so a finding may cite test_serializers.py:LINE instead of the test's name."""
    starts = [(m.group(1), source[: m.start()].count("\n") + 1) for m in re.finditer(r"^    (?:@.*\n    )?def (test_\w+)", source, re.M)]
    ends = [line - 1 for _, line in starts[1:]] + [source.count("\n") + 1]
    return {name: range(start, end + 1) for (name, start), end in zip(starts, ends)}


def cites(chunk: str, name: str, ranges: dict[str, range]) -> bool:
    if name in chunk:
        return True
    for a, b in re.findall(r"test_serializers\.py:(\d+)(?:[-–](\d+))?", chunk):
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
    unchanged = (ws / "orders" / "tests" / "serializers" / "test_serializers.py").read_text() == original
    result = {"found": sum(found.values()), "total": len(FINDINGS), "findings": found, "tests_unchanged": unchanged}
    (run_dir / "grading.json").write_text(json.dumps(result, indent=2))
    print(f"findings {sum(found.values())}/{len(FINDINGS)}; tests unchanged: {unchanged}")
    for name, ok in found.items():
        if not ok:
            print(f"  missed: {name}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
