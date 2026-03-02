"""Output helpers for CLI and integrations."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ArticleResult, BrowserTab, PageStatus


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(". ")
    return cleaned or "untitled"


def article_to_markdown(result: ArticleResult) -> str:
    lines = [
        f"# {result.title or 'Untitled'}",
        "",
        f"- Status: {result.status.value}",
        f"- Author: {result.author or 'Unknown'}",
        f"- URL: {result.url}",
    ]
    if result.publish_time:
        lines.append(f"- Publish Time: {result.publish_time}")
    if result.fetched_at:
        lines.append(f"- Fetched At: {result.fetched_at}")
    if result.hint and result.status != PageStatus.OK:
        lines.append(f"- Hint: {result.hint}")
    lines.extend(["", result.content or ""])
    return "\n".join(lines).rstrip() + "\n"


def result_to_json(result: ArticleResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


def tabs_to_json(tabs: list[BrowserTab]) -> str:
    return json.dumps([tab.to_dict() for tab in tabs], ensure_ascii=False, indent=2)


def save_markdown(result: ArticleResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = sanitize_filename(result.title or result.page_title or "untitled")
    candidate = output_dir / f"{base}.md"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{base}-{counter}.md"
        counter += 1
    candidate.write_text(article_to_markdown(result), encoding="utf-8")
    return candidate
