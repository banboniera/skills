"""Grade one review run: does the report find each weakness planted in review_spec.ts, without changing the spec?
Usage: python grade_review.py <run-dir> <workspace>
"""

import json
import re
import sys
from pathlib import Path

# (finding, patterns that must all appear in one paragraph, list item, or table row; a test title also matches an orders.spec.ts:LINE or bare :LINE citation)
FINDINGS = [
    ("list test uses CSS structure", ["lists orders", r"(?i)css|tbody|structure|getByRole|selector"]),
    ("search mock ignores the query", ["search by plate", r"(?i)ignor|same (rows|data|response)|regardless|always|every|query|param|plate=|uppercase|AB123"]),
    ("status filter asserts only a request count", ["status filter reloads the list", r"(?i)count|length|any request|status=|param|query|done"]),
    ("paging never checked with filters", [r"(?i)(pag|next)[^|\n]{0,200}(filter|status|search|plate)|(filter|status|search|plate)[^|\n]{0,200}(pag|next)"]),
    ("empty state read once with isVisible", ["shows empty state", r"(?i)isVisible|once|retry|race|web-first|flak"]),
    ("loading test passes trivially", ["shows loading state", r"(?i)trivial|always|never (held|holds|shows|asserts)|hold|delay|gate|absent|hidden|negative|anchor|in.flight"]),
    ("overdue uses the machine clock", ["marks overdue orders", r"(?i)clock|Date\.now|machine|time ?zone|UTC|midnight|setFixedTime|flak"]),
    ("overdue boundary untested", [r"(?i)today"]),
    ("viewer New order check has no anchor", ["viewers do not see New order", r"(?i)anchor|trivial|absent|before|render|loaded|never|always|vacuous|empty page|positive"]),
    ("viewer delete test asserts the bug", ["each order has a delete button", r"(?i)viewer|bug|should not|must not|promise|manager"]),
    ("delete test checks only the dialog", ["delete an order", r"(?i)request|DELETE /|row|removed|nth|position|path"]),
    ("create test sleeps and checks part of the body", ["create an order", r"(?i)waitForTimeout|sleep|500|objectContaining|partial|plate|due_date|whole body|EF789"]),
    ("validation test does not check nothing was sent", ["customer is required", r"(?i)no (POST|request)|nothing (was |is )?sent|not sent|request|POST"]),
    ("error state untested", [r"(?i)(error|fail|retry|500)[^|\n]{0,120}(state|untested|no test|not tested|missing|never|uncovered|alert)|Could not load"]),
]


def test_ranges(source: str) -> dict[str, range]:
    """Line range of each test, so a finding may cite orders.spec.ts:LINE instead of the test's title."""
    starts = [(m.group(1), source[: m.start()].count("\n") + 1) for m in re.finditer(r"^test\('([^']+)'", source, re.M)]
    ends = [line - 1 for _, line in starts[1:]] + [source.count("\n") + 1]
    return {name: range(start, end + 1) for (name, start), end in zip(starts, ends)}


def cites(chunk: str, name: str, ranges: dict[str, range]) -> bool:
    if name.lower() in chunk.lower():
        return True
    for a, b in re.findall(r"(?:orders\.spec\.ts|(?<![\w.]))[:L](\d+)(?:[-–](\d+))?", chunk):
        if set(range(int(a), int(b or a) + 1)) & set(ranges[name]):
            return True
    return False


def main(run_dir: Path, ws: Path) -> None:
    report = (run_dir / "report.md").read_text() if (run_dir / "report.md").exists() else ""
    # A finding may be one paragraph, list item, or table row, or a whole section under a heading.
    chunks = [c for c in re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.|\|)\s)", report) if c.strip()]
    chunks += [c for c in re.split(r"\n(?=#{1,4} )", report) if c.strip()]
    original = (Path(__file__).parent / "review_spec.ts").read_text()
    ranges = test_ranges(original)

    def hit(chunk: str, pats: list[str]) -> bool:
        return all(cites(chunk, p, ranges) if p in ranges else re.search(p, chunk) for p in pats)

    found = {name: any(hit(c, pats) for c in chunks) for name, pats in FINDINGS}
    unchanged = (ws / "e2e" / "orders.spec.ts").read_text() == original
    page_unchanged = (ws / "src" / "pages" / "orders.js").read_text() == (Path(__file__).parent / "fixture-workshop" / "src" / "pages" / "orders.js").read_text()
    result = {"found": sum(found.values()), "total": len(FINDINGS), "findings": found, "spec_unchanged": unchanged, "page_unchanged": page_unchanged}
    (run_dir / "grading.json").write_text(json.dumps(result, indent=2))
    print(f"findings {sum(found.values())}/{len(FINDINGS)}; spec unchanged: {unchanged}; page unchanged: {page_unchanged}")
    for name, ok in found.items():
        if not ok:
            print(f"  missed: {name}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
