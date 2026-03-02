#!/usr/bin/env python3
"""Thin OpenClaw-oriented wrapper around mp-article-bridge."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from wechat_reader.integrations.openclaw import openclaw_open_sync, openclaw_read_sync


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw bridge example for WeChat article access.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("open", "read"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("url")
        subparser.add_argument("--strategy", default="launch", choices=("auto", "attach", "launch", "playwright"))
        subparser.add_argument("--cdp-url")
        subparser.add_argument("--timeout", type=int, default=30)
        subparser.add_argument("--wait-for-manual-verify", type=int, default=90)
        subparser.add_argument("--channel", default="chrome", choices=("chrome", "chromium"))
        subparser.add_argument("--profile-dir", type=Path)
        subparser.add_argument("--profile-name", default="default")
        subparser.add_argument("--ephemeral", action="store_true")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    kwargs = {
        "strategy": args.strategy,
        "cdp_url": args.cdp_url,
        "timeout": args.timeout,
        "wait_for_manual_verify": args.wait_for_manual_verify,
        "channel": args.channel,
        "profile_dir": args.profile_dir,
        "profile_name": args.profile_name,
        "ephemeral": args.ephemeral,
    }

    if args.command == "open":
        payload = openclaw_open_sync(args.url, **kwargs)
    else:
        payload = openclaw_read_sync(args.url, **kwargs)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
