"""Invoice item metadata."""

def line_codes(lines: list[dict[str, str]]) -> list[str]:
    return [line["code"] for line in lines]
