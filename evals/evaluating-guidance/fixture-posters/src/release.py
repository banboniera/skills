import argparse
import json
from pathlib import Path


def release(output, content, *, replace=False, approved=False):
    replaced = output.exists()
    with output.open("w" if replace else "x") as edition:
        edition.write(content)
    output.with_suffix(".receipt.json").write_text(
        json.dumps({"replaced": replaced, "approved": approved})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("content")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    release(args.output, args.content, replace=args.replace, approved=args.approved)
