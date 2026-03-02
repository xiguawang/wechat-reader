"""CLI entrypoint for wechat-reader."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .browser_bridge import (
    DEFAULT_TIMEOUT_SECONDS,
    list_wechat_tabs_sync,
    open_article_sync,
    read_article_sync,
)
from .formatters import article_to_markdown, result_to_json, save_markdown, tabs_to_json
from .models import PageStatus, Strategy
from .setup import format_setup_report, run_setup_diagnostics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local browser bridge for reading WeChat articles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read", help="Read a WeChat article, opening it if needed.")
    _add_browser_args(read_parser)
    read_parser.add_argument("url")
    read_parser.add_argument("--json", action="store_true", dest="as_json")
    read_parser.add_argument("--output", type=Path)

    open_parser = subparsers.add_parser("open", help="Open a WeChat article and report current page status.")
    _add_browser_args(open_parser)
    open_parser.add_argument("url")
    open_parser.add_argument("--json", action="store_true", dest="as_json")

    tabs_parser = subparsers.add_parser("tabs", help="List attachable browser tabs.")
    tabs_parser.add_argument("--cdp-url")
    tabs_parser.add_argument("--wechat-only", action="store_true")
    tabs_parser.add_argument("--json", action="store_true", dest="as_json")

    setup_parser = subparsers.add_parser("setup", help="Diagnose browser bridge prerequisites.")
    setup_parser.add_argument("--json", action="store_true", dest="as_json")

    return parser


def _add_browser_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--strategy", choices=[item.value for item in Strategy], default=Strategy.AUTO.value)
    parser.add_argument("--cdp-url")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--wait-for-manual-verify", type=int, default=0)
    parser.add_argument("--channel", choices=("chrome", "chromium"), default="chrome")
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--profile-name", default="default")
    parser.add_argument("--ephemeral", action="store_true")


def _print(text: str) -> None:
    print(text, end="" if text.endswith("\n") else "\n")


def _exit_code_for_status(status: PageStatus) -> int:
    return 0 if status == PageStatus.OK else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "read":
        if args.wait_for_manual_verify > 0:
            print(
                f"Waiting up to {args.wait_for_manual_verify}s for manual verification if WeChat blocks the page...",
                file=sys.stderr,
            )
        result = read_article_sync(
            args.url,
            strategy=args.strategy,
            cdp_url=args.cdp_url,
            timeout=args.timeout,
            wait_for_manual_verify=args.wait_for_manual_verify,
            channel=args.channel,
            profile_dir=args.profile_dir,
            profile_name=args.profile_name,
            ephemeral=args.ephemeral,
        )
        if args.output and result.status == PageStatus.OK:
            save_path = save_markdown(result, args.output)
            print(f"Saved: {save_path}", file=sys.stderr)
        _print(result_to_json(result) if args.as_json else article_to_markdown(result))
        return _exit_code_for_status(result.status)

    if args.command == "open":
        if args.wait_for_manual_verify > 0:
            print(
                f"Waiting up to {args.wait_for_manual_verify}s for manual verification if WeChat blocks the page...",
                file=sys.stderr,
            )
        result = open_article_sync(
            args.url,
            strategy=args.strategy,
            cdp_url=args.cdp_url,
            timeout=args.timeout,
            wait_for_manual_verify=args.wait_for_manual_verify,
            channel=args.channel,
            profile_dir=args.profile_dir,
            profile_name=args.profile_name,
            ephemeral=args.ephemeral,
        )
        _print(result_to_json(result) if args.as_json else article_to_markdown(result))
        return _exit_code_for_status(result.status)

    if args.command == "tabs":
        tabs = list_wechat_tabs_sync(args.cdp_url, wechat_only=args.wechat_only)
        if args.as_json:
            _print(tabs_to_json(tabs))
        else:
            for tab in tabs:
                _print(f"{tab.id or '-'}\t{tab.title}\t{tab.url}")
        return 0

    if args.command == "setup":
        report = run_setup_diagnostics()
        if args.as_json:
            _print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print(format_setup_report(report))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
