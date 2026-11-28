import json
import sys
from pathlib import Path


if __name__ == "__main__":
    receipt = json.loads(Path(sys.argv[1]).read_text())
    if receipt["replaced"] and not receipt["approved"]:
        sys.exit("Release replaced an edition without approval; use an unused output path.")
