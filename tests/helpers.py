import io
from collections.abc import Iterator


class _RecordingTextStream:
    """Fake console stream that records reconfigure() calls and encodes writes."""

    def __init__(self, encoding: str = "cp936", errors: str = "strict", input_text: str = "") -> None:
        self.encoding = encoding
        self._errors = errors
        self._buffer = io.BytesIO()
        self._input_text = input_text
        self.reconfigure_calls: list[dict[str, str | None]] = []

    def reconfigure(self, *, encoding: str | None = None, errors: str | None = None) -> None:
        self.reconfigure_calls.append({"encoding": encoding, "errors": errors})
        if encoding is not None:
            self.encoding = encoding
        if errors is not None:
            self._errors = errors

    def write(self, text: str) -> int:
        data = text.encode(self.encoding, self._errors)
        self._buffer.write(data)
        return len(data)

    def flush(self) -> None:
        pass

    def read(self) -> str:
        return self._input_text

    def __iter__(self) -> Iterator[str]:
        return iter(self._input_text.splitlines(keepends=True))

    def getvalue(self) -> str:
        return self._buffer.getvalue().decode(self.encoding, "replace")
