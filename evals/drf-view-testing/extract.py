"""Write the agent's report from an omp --mode json event stream to <run-dir>/report.md.
The report is every assistant message without tool calls, joined: an advisor can prompt follow-ups after the first one.
Usage: python extract.py <run-dir>
"""

import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
parts = []
for line in (run_dir / "events.jsonl").read_text().splitlines():
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    message = event.get("message") or {}
    content = message.get("content")
    if event.get("type") != "message_end" or message.get("role") != "assistant" or not isinstance(content, list):
        continue
    if any(c.get("type") == "toolCall" for c in content):
        continue
    text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
    if text.strip():
        parts.append(text)
(run_dir / "report.md").write_text("\n\n".join(parts))
