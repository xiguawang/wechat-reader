"""Helpers for configuring text streams used by command-line entry points."""

from __future__ import annotations

import sys


def _configure_stdio_utf8() -> None:
    """Use UTF-8 for Windows entry-point stdio streams."""

    if sys.platform != "win32":
        return

    # Windows consoles default to GBK/cp936, which cannot encode all Unicode
    # characters (e.g. \xa0 non-breaking spaces common in article bodies).
    # Force UTF-8 there so protocol and article content do not raise
    # UnicodeEncodeError; errors="replace" also covers lone surrogates that
    # even UTF-8 cannot encode. Replace malformed input characters so a bad
    # byte cannot kill the JSON-RPC loop. Other platforms keep the user's
    # locale and PYTHONIOENCODING untouched. Note: this makes redirected
    # stdout UTF-8 even on Chinese Windows, so pipe output to files opened as
    # UTF-8.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
