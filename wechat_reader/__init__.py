"""Public package exports for wechat-reader."""

from .browser_bridge import (
    list_wechat_tabs,
    list_wechat_tabs_sync,
    open_article,
    open_article_sync,
    read_article,
    read_article_sync,
)
from .models import ArticleResult, BrowserTab, PageStatus, Strategy
from .setup import format_setup_report, run_setup_diagnostics

__all__ = [
    "ArticleResult",
    "BrowserTab",
    "PageStatus",
    "Strategy",
    "format_setup_report",
    "list_wechat_tabs",
    "list_wechat_tabs_sync",
    "open_article",
    "open_article_sync",
    "read_article",
    "read_article_sync",
    "run_setup_diagnostics",
]
