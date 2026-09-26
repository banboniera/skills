"""Write the agent's final answer from an omp --mode json event stream to <run-dir>/report.md.
Usage: python extract.py <run-dir>
"""

import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
final = ""
for line in (run_dir / "events.jsonl").read_text().splitlines():
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    message = event.get("message") or {}
    if event.get("type") == "message_end" and message.get("role") == "assistant":
        text = "\n".join(c.get("text", "") for c in message.get("content", []) if c.get("type") == "text")
        if text.strip():
            final = text
(run_dir / "report.md").write_text(final)
