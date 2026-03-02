"""Core datatypes for wechat-reader."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class PageStatus(StrEnum):
    OK = "ok"
    CAPTCHA_REQUIRED = "captcha_required"
    RATE_LIMITED = "rate_limited"
    ARTICLE_NOT_RENDERED = "article_not_rendered"
    UNSUPPORTED_PAGE = "unsupported_page"
    BROWSER_NOT_READY = "browser_not_ready"
    BROWSER_NOT_FOUND = "browser_not_found"
    NAVIGATION_FAILED = "navigation_failed"


class Strategy(StrEnum):
    AUTO = "auto"
    ATTACH = "attach"
    LAUNCH = "launch"
    PLAYWRIGHT = "playwright"


@dataclass(slots=True)
class BrowserTab:
    id: str | None
    title: str
    url: str
    kind: str = "page"
    profile: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArticleResult:
    status: PageStatus
    url: str
    title: str = ""
    author: str = ""
    content: str = ""
    html: str | None = None
    publish_time: str | None = None
    account_name: str | None = None
    fetched_at: str | None = None
    hint: str | None = None
    target_id: str | None = None
    page_title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def status_only(
        cls,
        status: PageStatus,
        url: str,
        *,
        hint: str | None = None,
        page_title: str | None = None,
        target_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ArticleResult":
        return cls(
            status=status,
            url=url,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            hint=hint,
            page_title=page_title,
            target_id=target_id,
            metadata=metadata or {},
        )
