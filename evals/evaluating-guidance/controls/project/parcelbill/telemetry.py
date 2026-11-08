"""Per-operation event capture used by the service adapter."""
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator

_current: ContextVar[list[dict[str, str]] | None] = ContextVar("events", default=None)


def record(kind: str, subject: str) -> None:
    events = _current.get()
    if events is not None:
        events.append({"kind": kind, "subject": subject})


@contextmanager
def capture() -> Iterator[list[dict[str, str]]]:
    events: list[dict[str, str]] = []
    token = _current.set(events)
    try:
        yield events
    finally:
        _current.reset(token)
