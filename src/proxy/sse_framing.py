"""Generic Server-Sent Events (SSE) framing — WHATWG SSE line/event
rules only. No knowledge of OpenAI's chat-completion-chunk schema
belongs here; that lives in chat_stream.py, one layer up.

Two explicit state machines, composed: `_LineSplitter` turns arbitrary
text fragments into complete lines (handling \\r\\n, bare \\n, and bare
\\r, including a \\r\\n pair split exactly across two feed() calls);
`SSEEventParser` turns lines into events per the spec's dispatch rule
(a blank line terminates the current event; `data:` lines accumulate,
joined by "\\n" if there is more than one).
"""

from dataclasses import dataclass

_DATA_FIELD = "data:"


@dataclass(frozen=True)
class SSEEvent:
    """One complete SSE event: the concatenated `data:` field value(s).

    `event:`/`id:`/`retry:` fields and comment lines (leading `:`) are
    recognized while parsing — so the parser does not error on them —
    but discarded. OpenAI's chat-completions stream never sends them;
    modeling a field this module never needs is a decision for whoever
    needs it, not a default to build in now.
    """

    data: str


class _LineSplitter:
    """Splits fed text into lines on \\r\\n, bare \\n, or bare \\r.

    The one genuinely tricky case: a \\r\\n pair split exactly across
    two feed() calls must be recognized as a single line terminator,
    not two. A trailing \\r with nothing after it yet is therefore held
    back — not resolved as a terminator — until either the next
    character arrives (revealing whether it completes a \\r\\n pair) or
    flush() confirms no more data is coming.
    """

    def __init__(self) -> None:
        self._buffer: list[str] = []
        self._pending_cr = False

    def feed(self, chunk: str) -> list[str]:
        lines: list[str] = []
        for ch in chunk:
            if self._pending_cr:
                self._pending_cr = False
                if ch == "\n":
                    continue  # completed \r\n pair; already terminated when \r arrived
            if ch == "\r":
                lines.append("".join(self._buffer))
                self._buffer = []
                self._pending_cr = True
            elif ch == "\n":
                lines.append("".join(self._buffer))
                self._buffer = []
            else:
                self._buffer.append(ch)
        return lines

    def flush(self) -> list[str]:
        """Stream end: any partial line becomes a final line."""
        self._pending_cr = False
        if not self._buffer:
            return []
        line = "".join(self._buffer)
        self._buffer = []
        return [line]


class SSEEventParser:
    """Incremental SSE event parser: text fragments in, complete events
    out, correct regardless of where the fragmentation lands.
    """

    def __init__(self) -> None:
        self._lines = _LineSplitter()
        self._data_lines: list[str] = []

    def feed(self, chunk: str) -> list[SSEEvent]:
        """Feed a raw text fragment; return any events it completed.

        Returns an empty list if the fragment only advanced a partial
        line or a partial event — not an error, just nothing dispatched
        yet.
        """
        return [
            event
            for line in self._lines.feed(chunk)
            if (event := self._handle_line(line)) is not None
        ]

    def flush(self) -> list[SSEEvent]:
        """Stream end: dispatch any event still pending.

        A stream that ends without a final blank line still has a
        pending event if any `data:` lines were accumulated — dispatch
        it now rather than silently dropping the last event, the same
        "flush is not optional" invariant SlidingWindow enforces one
        layer up.
        """
        events = [
            event for line in self._lines.flush() if (event := self._handle_line(line)) is not None
        ]
        if self._data_lines:
            events.append(self._dispatch())
        return events

    def _handle_line(self, line: str) -> SSEEvent | None:
        if line == "":
            return self._dispatch() if self._data_lines else None
        if line.startswith(":"):
            return None  # comment line, per spec
        if line.startswith(_DATA_FIELD):
            value = line[len(_DATA_FIELD) :]
            if value.startswith(" "):
                value = value[1:]  # exactly one leading space stripped, per spec
            self._data_lines.append(value)
            return None
        return None  # event:/id:/retry:/unrecognized field — discarded

    def _dispatch(self) -> SSEEvent:
        data = "\n".join(self._data_lines)
        self._data_lines = []
        return SSEEvent(data=data)
