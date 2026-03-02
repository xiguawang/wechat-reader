"""Stable OpenClaw exec wrapper for wechat-reader."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .integrations.openclaw import openclaw_open_sync, openclaw_read_sync
from .setup import run_setup_diagnostics


DEFAULT_WAIT_FOR_MANUAL_VERIFY = 90


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw exec wrapper for wechat-reader.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    schema_parser = subparsers.add_parser("schema", help="Print wrapper input schema.")
    schema_parser.add_argument("--pretty", action="store_true")

    setup_parser = subparsers.add_parser("setup", help="Run setup diagnostics for agent use.")
    setup_parser.add_argument("--pretty", action="store_true")

    for command in ("open", "read"):
        subparser = subparsers.add_parser(command, help=f"{command.title()} a WeChat article through the bridge.")
        subparser.add_argument("url", nargs="?")
        subparser.add_argument("--strategy", default="launch", choices=("auto", "attach", "launch", "playwright"))
        subparser.add_argument("--cdp-url")
        subparser.add_argument("--timeout", type=int, default=30)
        subparser.add_argument("--wait-for-manual-verify", type=int, default=DEFAULT_WAIT_FOR_MANUAL_VERIFY)
        subparser.add_argument("--channel", default="chrome", choices=("chrome", "chromium"))
        subparser.add_argument("--profile-dir", type=Path)
        subparser.add_argument("--profile-name", default="default")
        subparser.add_argument("--ephemeral", action="store_true")
        subparser.add_argument("--stdin-json", action="store_true", help="Read arguments from JSON on stdin.")
        subparser.add_argument("--pretty", action="store_true")

    return parser


def input_schema() -> dict[str, Any]:
    return {
        "tool": "wechat-reader-openclaw",
        "description": "Read WeChat article URLs through a local visible browser bridge.",
        "commands": {
            "read": {
                "required": ["url"],
                "optional": [
                    "strategy",
                    "cdp_url",
                    "timeout",
                    "wait_for_manual_verify",
                    "channel",
                    "profile_dir",
                    "profile_name",
                    "ephemeral",
                ],
            },
            "open": {
                "required": ["url"],
                "optional": [
                    "strategy",
                    "cdp_url",
                    "timeout",
                    "wait_for_manual_verify",
                    "channel",
                    "profile_dir",
                    "profile_name",
                    "ephemeral",
                ],
            },
            "setup": {"required": [], "optional": []},
        },
    }


def _load_stdin_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("stdin JSON must be an object")
    return payload


def _resolve_value(
    args: argparse.Namespace,
    payload: dict[str, Any],
    cli_name: str,
    *,
    default: Any,
    json_name: str | None = None,
) -> Any:
    json_key = json_name or cli_name.replace("-", "_")
    value = getattr(args, cli_name.replace("-", "_"))
    if value != default:
        return value
    if json_key in payload:
        return payload[json_key]
    return default


def _command_kwargs(args: argparse.Namespace, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    url = args.url if args.url else payload.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url is required")

    profile_dir = _resolve_value(args, payload, "profile_dir", default=None)
    return url, {
        "strategy": _resolve_value(args, payload, "strategy", default="launch"),
        "cdp_url": _resolve_value(args, payload, "cdp_url", default=None),
        "timeout": int(_resolve_value(args, payload, "timeout", default=30)),
        "wait_for_manual_verify": int(
            _resolve_value(
                args,
                payload,
                "wait_for_manual_verify",
                default=DEFAULT_WAIT_FOR_MANUAL_VERIFY,
                json_name="wait_for_manual_verify",
            )
        ),
        "channel": _resolve_value(args, payload, "channel", default="chrome"),
        "profile_dir": Path(profile_dir) if isinstance(profile_dir, str) and profile_dir else profile_dir,
        "profile_name": _resolve_value(args, payload, "profile_name", default="default"),
        "ephemeral": bool(_resolve_value(args, payload, "ephemeral", default=False)),
    }


def _print_payload(payload: dict[str, Any], *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))


def _error_payload(message: str) -> dict[str, Any]:
    return {
        "tool": "wechat-reader-openclaw",
        "status": "invalid_input",
        "next_action": "fix_tool_input",
        "user_message": message,
        "hint": message,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "schema":
        _print_payload(input_schema(), pretty=args.pretty)
        return 0

    if args.command == "setup":
        payload = {
            "tool": "wechat-reader-openclaw",
            "status": "ok",
            "next_action": "inspect_setup",
            "setup": run_setup_diagnostics(),
        }
        _print_payload(payload, pretty=args.pretty)
        return 0

    try:
        stdin_payload = _load_stdin_payload() if args.stdin_json else {}
        url, kwargs = _command_kwargs(args, stdin_payload)
        if args.command == "open":
            payload = openclaw_open_sync(url, **kwargs)
        else:
            payload = openclaw_read_sync(url, **kwargs)
    except (ValueError, json.JSONDecodeError) as exc:
        _print_payload(_error_payload(str(exc)), pretty=True)
        return 0

    _print_payload(payload, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
