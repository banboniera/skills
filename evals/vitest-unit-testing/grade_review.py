"""Grade one review run: does the report find each weakness planted in review/, without changing the tests or the code?
Usage: python grade_review.py <run-dir> <workspace>
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
# (finding, patterns that must all appear in one paragraph, list item, or table row, or one section under a heading;
#  a quoted test name also matches a <file>:LINE citation inside that test)
FINDINGS = [
    ("formatMoney checked with toContain", [r"(?i)formats money|formatMoney", r"(?i)toContain|loose|partial|exact|negative|pad|currenc"]),
    ("parseAmount misses one-decimal and rejections", [r"(?i)parses amounts|parseAmount", r"(?i)12[.,]5\b|one[- ]digit|single|one decimal|reject|refus|null|invalid|comma"]),
    ("hook test waits on real time", ["updates after the delay", r"(?i)real (time|timer)|fake timer|useFakeTimers|setTimeout\(resolve|slow|flak|350"]),
    ("hook test never checks before the delay", ["updates after the delay", r"(?i)before|299|too early|restart|each change|still|old value|immediately|delay ?- ?1|boundary"]),
    ("list test checks only that fetch ran", ["lists invoices", r"(?i)toHaveBeenCalled\b|called|url|query|param|page_size|path|request"]),
    ("status all never tested", [r"(?i)(status[^|\n]{0,80}\ball\b|\ball\b[^|\n]{0,80}status)"]),
    ("catch assertion never runs", ["rejects paying an invoice twice", r"(?i)never (runs|executes|called|reached)|catch|expect\.assertions|hasAssertions|resolv|succeed|200|passes"]),
    ("render test uses toBeTruthy", ["renders", r"(?i)toBeTruthy|heading|getByRole|toBeInTheDocument|weak|trivial"]),
    ("submit test checks no payload", ["submits", r"(?i)payload|arguments|args|toHaveBeenCalledWith|values|amount_cents|1250|exact"]),
    ("fireEvent instead of user-event", [r"(?i)fireEvent", r"(?i)user-?event|userEvent"]),
    ("validation test does not check nothing was submitted", ["validates the customer", r"(?i)not\.toHaveBeenCalled|not (called|submitted)|nothing (was |is )?(sent|submitted)|onSubmit"]),
    ("server error test asserts the bug", ["keeps the form locked after server field errors", r"(?i)bug|enabled|should (be|re)|re-?enable|promise|stays? disabled|locked"]),
    ("date input found by querySelector", [r"(?i)querySelector|container", r"(?i)label|getByLabelText|role|accessib"]),
    ("cancel, saving state, and general error untested", [r"(?i)cancel|Saving…|saving state|pending|general error|Could not save"]),
]


def test_ranges(files: dict[str, str]) -> dict[str, tuple[str, range]]:
    """File and line range of each test, so a finding may cite <file>:LINE instead of the test's name."""
    ranges = {}
    for file, source in files.items():
        starts = [(m.group(1), source[: m.start()].count("\n") + 1) for m in re.finditer(r"^\s*it\('([^']+)'", source, re.M)]
        ends = [line - 1 for _, line in starts[1:]] + [source.count("\n") + 1]
        for (name, start), end in zip(starts, ends):
            ranges[name] = (file, range(start, end + 1))
    return ranges


def cites(chunk: str, name: str, ranges: dict[str, tuple[str, range]]) -> bool:
    if re.search(rf"['\"`‘“]{re.escape(name)}['\"`’”]", chunk, re.I):
        return True
    file, lines = ranges[name]
    # A section about the test's file, when that file holds a single test.
    if sum(f == file for f, _ in ranges.values()) == 1 and Path(file).name in chunk:
        return True
    for a, b in re.findall(rf"{re.escape(Path(file).name)}:(\d+)(?:[-–](\d+))?", chunk):
        if set(range(int(a), int(b or a) + 1)) & set(lines):
            return True
    return False


def main(run_dir: Path, ws: Path) -> None:
    report = (run_dir / "report.md").read_text() if (run_dir / "report.md").exists() else ""
    chunks = [c for c in re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.|\|)\s)", report) if c.strip()]
    chunks += [c for c in re.split(r"\n(?=#{1,4} |\*\*[^*\n]+\*\*\s*\n)", report) if c.strip()]
    originals = {str(p.relative_to(HERE / "review")): p.read_text() for p in (HERE / "review").rglob("*.test.ts*")}
    ranges = test_ranges(originals)

    def hit(chunk: str, pats: list[str]) -> bool:
        return all(cites(chunk, p, ranges) if p in ranges else re.search(p, chunk) for p in pats)

    found = {name: any(hit(c, pats) for c in chunks) for name, pats in FINDINGS}
    tests_unchanged = all((ws / file).read_text() == source for file, source in originals.items())
    fixture = HERE / "fixture-billing"
    code_unchanged = all((ws / p.relative_to(fixture)).read_text() == p.read_text() for p in (fixture / "src").rglob("*.ts*") if ".test." not in p.name)
    result = {"found": sum(found.values()), "total": len(FINDINGS), "findings": found, "tests_unchanged": tests_unchanged, "code_unchanged": code_unchanged}
    (run_dir / "grading.json").write_text(json.dumps(result, indent=2))
    print(f"findings {sum(found.values())}/{len(FINDINGS)}; tests unchanged: {tests_unchanged}; code unchanged: {code_unchanged}")
    for name, ok in found.items():
        if not ok:
            print(f"  missed: {name}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
