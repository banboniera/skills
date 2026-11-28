from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import shutil
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


def materialize(scenario, bucket, project):
    for began, slug, timeline in json.loads(scenario.read_text()):
        start = datetime.fromisoformat(began).replace(tzinfo=UTC)
        rows = []
        session_id = str(uuid5(NAMESPACE_URL, f"poster-catalog:{began}:{slug}"))

        def emit(kind, **fields):
            index = len(rows)
            stamp = start + timedelta(seconds=index)
            row = {"type": kind, "timestamp": stamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")}
            if kind != "session":
                row.update(id=f"{index:08x}", parentId=rows[-1]["id"] if index > 1 else None)
            if "message" in fields:
                fields["message"]["timestamp"] = int(stamp.timestamp() * 1000)
            rows.append(row | fields)

        def say(role, content, **fields):
            emit("message", message={"role": role, "content": content, **fields})

        emit("session", version=3, id=session_id, cwd=str(project), title=slug.replace("-", " "))
        for kind, *args in timeline:
            if kind in {"assistant", "user"}:
                fields = {"stopReason": "stop"} if kind == "assistant" else {}
                say(kind, [{"type": "text", "text": args[0].replace("@@PROJECT@@", str(project))}], **fields)
            elif kind in {"tool", "call"}:
                name, arguments, *result = args
                call_id = f"call_{len(rows):08x}"
                say("assistant", [{"type": "toolCall", "id": call_id, "name": name, "arguments": arguments}],
                    stopReason="toolUse")
                if result:
                    say("toolResult", [{"type": "text", "text": result[0]}], toolName=name,
                        toolCallId=call_id, isError=bool(result[1:]))
            elif kind in {"interrupt", "judged", "pruned"}:
                rules = args[0]
                content = ""
                details = {"rules": rules}
                if kind != "pruned":
                    matched, instruction = args[1:]
                    tag = "interrupt" if kind == "interrupt" else "reminder"
                    notice = "Output interrupted." if kind == "interrupt" else "Rule judge flagged this edit."
                    content = "\n".join(
                        f'<system-{tag} reason="rule_violation" rule="{rule}" path=".omp/rules/{rule}.md">\n'
                        f'{notice}\nMatched: "{matched}"\n{instruction}\n</system-{tag}>'
                        for rule in rules
                    )
                    details["matched"] = dict.fromkeys(rules, matched)
                emit("custom_message", customType="ttsr-injection", content=content, display=True, details=details)
                emit("ttsr_injection", injectedRules=rules if kind != "pruned" else [])
            else:
                raise ValueError(f"Unknown event kind: {kind}")
        filename = start.strftime("%Y-%m-%dT%H-%M-%S-000Z") + f"_{session_id}.jsonl"
        (bucket / filename).write_text("".join(json.dumps(row) + "\n" for row in rows))


def prior_review(project, since, until, sessions):
    state = project / ".trial-state"
    state.mkdir()
    history = (project / ".trial-sessions").resolve()
    name = sha256(f"{project}\n{history}".encode()).hexdigest() + ".json"
    (state / name).write_text(json.dumps({
        "project": str(project), "since": since + "T00:00:00.000000", "until": until + "T00:00:00.000000",
        "sessions": int(sessions), "recorded_at": until + "T00:15:00+00:00",
    }) + "\n")


cwd = Path.cwd()
source = cwd / "history"
if len(sys.argv) > 1:
    home = str(Path.home())
    path = str(cwd)
    if path.startswith(home + "/"):
        encoded = path[len(home):].replace("/", "-")
    elif path.startswith("/tmp/"):
        encoded = path.replace("/", "-")
    else:
        encoded = f"--{path.lstrip('/').replace('/', '-')}--"
    bucket = cwd / ".trial-sessions" / encoded
    bucket.mkdir(parents=True)
    scenario = source / f"{sys.argv[1]}.json"
    if scenario.is_file():
        materialize(scenario, bucket, cwd)
    else:
        transcripts = sorted((source / sys.argv[1]).glob("*.jsonl"))
        if not transcripts:
            sys.exit("No synthetic sessions for this scenario")
        for transcript in transcripts:
            header, entries = transcript.read_text().split("\n", 1)
            session = json.loads(header)
            session["cwd"] = str(cwd)
            (bucket / transcript.name).write_text(f"{json.dumps(session)}\n{entries}")
    if len(sys.argv) > 2:
        prior_review(cwd, *sys.argv[2:])
shutil.rmtree(source)
Path(__file__).unlink()
