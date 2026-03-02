"""WeChat page detection and DOM extraction."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

from .models import ArticleResult, PageStatus

CAPTCHA_KEYWORD = "wappoc_appmsgcaptcha"
RATE_LIMIT_PATTERNS = (
    "environment abnormal",
    "environment exception",
    "environment is abnormal",
    "current environment is abnormal",
    "operation too frequent",
    "too frequent",
    "环境异常",
    "操作频繁",
)
VERIFY_PATTERNS = ("go verify", "去验证", "完成验证")
POLL_INTERVAL_SECONDS = 0.5


def normalize_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def read_dom_payload(page: Any) -> dict[str, str]:
    return page.evaluate(
        """
        () => {
          const text = (selector) => {
            const node = document.querySelector(selector);
            return node ? node.textContent.trim() : "";
          };
          const attr = (selector, name) => {
            const node = document.querySelector(selector);
            return node ? (node.getAttribute(name) || "").trim() : "";
          };
          const meta = (propertyName) => {
            const node = document.querySelector(`meta[property="${propertyName}"]`);
            return node ? (node.content || "").trim() : "";
          };
          const contentNode = document.getElementById("js_content");
          return {
            title: text("#activity-name") || meta("og:title") || document.title || "",
            author: text("#js_name") || "",
            account_name: text("#profileBt .profile_nickname") || text(".wx_profile_nickname") || "",
            content: contentNode ? contentNode.innerText.trim() : "",
            html: contentNode ? contentNode.innerHTML : "",
            publish_time: attr("#publish_time", "data-time") || text("#publish_time") || "",
            body_text: document.body ? document.body.innerText.trim() : "",
            page_title: document.title || "",
          };
        }
        """
    )


def classify_page(url: str, payload: dict[str, str]) -> tuple[PageStatus, str | None]:
    body_text = normalize_whitespace(payload.get("body_text", "")).lower()
    page_title = normalize_whitespace(payload.get("page_title", ""))
    current_url = url.lower()

    if CAPTCHA_KEYWORD in current_url:
        return PageStatus.CAPTCHA_REQUIRED, "Please complete verification in the browser, then retry."
    if any(pattern in body_text for pattern in VERIFY_PATTERNS):
        return PageStatus.CAPTCHA_REQUIRED, normalize_whitespace(payload.get("body_text", ""))[:200]
    if any(pattern in body_text for pattern in RATE_LIMIT_PATTERNS):
        return PageStatus.RATE_LIMITED, normalize_whitespace(payload.get("body_text", ""))[:200]
    if "mp.weixin.qq.com" not in current_url:
        return PageStatus.UNSUPPORTED_PAGE, "The current page is not a WeChat article page."
    if page_title and "wechat public platform" in page_title.lower():
        return PageStatus.ARTICLE_NOT_RENDERED, "The article shell loaded, but content is not available yet."
    return PageStatus.ARTICLE_NOT_RENDERED, "The article has not finished rendering."


def payload_to_result(url: str, payload: dict[str, str], *, target_id: str | None = None) -> ArticleResult:
    content = payload.get("content", "").strip()
    if content:
        author = normalize_whitespace(payload.get("author")) or normalize_whitespace(payload.get("account_name")) or "Unknown"
        return ArticleResult(
            status=PageStatus.OK,
            url=url,
            title=normalize_whitespace(payload.get("title")) or "Untitled",
            author=author,
            account_name=normalize_whitespace(payload.get("account_name")) or author,
            content=content,
            html=payload.get("html") or None,
            publish_time=normalize_whitespace(payload.get("publish_time")) or None,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            target_id=target_id,
            page_title=normalize_whitespace(payload.get("page_title")) or None,
        )

    status, hint = classify_page(url, payload)
    return ArticleResult.status_only(
        status,
        url=url,
        hint=hint,
        page_title=normalize_whitespace(payload.get("page_title")) or None,
        target_id=target_id,
    )


def wait_for_article_result(
    page: Any,
    timeout_ms: int,
    playwright_error: type[BaseException],
    *,
    target_id: str | None = None,
) -> ArticleResult:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            payload = read_dom_payload(page)
        except playwright_error as exc:
            last_error = exc
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        result = payload_to_result(page.url, payload, target_id=target_id)
        if result.status != PageStatus.ARTICLE_NOT_RENDERED:
            return result
        time.sleep(POLL_INTERVAL_SECONDS)

    if last_error is not None:
        return ArticleResult.status_only(
            PageStatus.NAVIGATION_FAILED,
            url=page.url,
            hint=f"Browser evaluation failed: {last_error}",
            target_id=target_id,
        )

    try:
        page_title = getattr(page, "title", lambda: "")()
    except playwright_error as exc:
        return ArticleResult.status_only(
            PageStatus.NAVIGATION_FAILED,
            url=page.url,
            hint=f"Browser evaluation failed: {exc}",
            target_id=target_id,
        )

    payload = {"page_title": page_title}
    return ArticleResult.status_only(
        PageStatus.ARTICLE_NOT_RENDERED,
        url=page.url,
        hint="Timed out waiting for article content.",
        page_title=normalize_whitespace(payload.get("page_title")),
        target_id=target_id,
    )


def wait_for_manual_resolution(
    page: Any,
    timeout_ms: int,
    playwright_error: type[BaseException],
    *,
    target_id: str | None = None,
) -> ArticleResult:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_result: ArticleResult | None = None
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            payload = read_dom_payload(page)
        except playwright_error as exc:
            last_error = exc
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        result = payload_to_result(page.url, payload, target_id=target_id)
        last_result = result
        if result.status == PageStatus.OK:
            return result
        if result.status == PageStatus.UNSUPPORTED_PAGE:
            return result
        time.sleep(POLL_INTERVAL_SECONDS)

    if last_result is not None:
        if last_result.status in {PageStatus.CAPTCHA_REQUIRED, PageStatus.RATE_LIMITED}:
            last_result.hint = "Manual verification timed out. Complete verification in the browser, then retry."
        elif last_result.status == PageStatus.ARTICLE_NOT_RENDERED:
            last_result.hint = "Timed out waiting for the WeChat page to become readable."
        return last_result

    if last_error is not None:
        return ArticleResult.status_only(
            PageStatus.NAVIGATION_FAILED,
            url=page.url,
            hint=f"Browser evaluation failed: {last_error}",
            target_id=target_id,
        )

    return ArticleResult.status_only(
        PageStatus.CAPTCHA_REQUIRED,
        url=page.url,
        hint="Manual verification timed out. Complete verification in the browser, then retry.",
        target_id=target_id,
    )
