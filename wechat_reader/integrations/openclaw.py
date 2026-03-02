"""OpenClaw-oriented wrappers for wechat-reader."""

from __future__ import annotations

from typing import Any

from ..browser_bridge import open_article_sync, read_article_sync
from ..models import ArticleResult, PageStatus


def _article_payload(result: ArticleResult) -> dict[str, Any]:
    return {
        "url": result.url,
        "title": result.title,
        "author": result.author,
        "content": result.content,
        "publish_time": result.publish_time,
        "fetched_at": result.fetched_at,
    }


def build_openclaw_response(result: ArticleResult) -> dict[str, Any]:
    next_action = "show_error"
    user_message = result.hint or "WeChat article access failed."
    hint_text = (result.hint or "").lower()

    if result.status == PageStatus.OK:
        next_action = "return_article"
        user_message = f"Read WeChat article: {result.title or result.page_title or result.url}"
    elif result.status == PageStatus.CAPTCHA_REQUIRED:
        next_action = "ask_user_to_verify"
        user_message = (
            result.hint
            or "The article opened in the bridge browser, but WeChat requires verification."
        )
    elif result.status == PageStatus.RATE_LIMITED:
        next_action = "ask_user_to_retry"
        user_message = result.hint or "WeChat temporarily rate-limited this page. Retry later."
    elif result.status == PageStatus.ARTICLE_NOT_RENDERED:
        next_action = "retry_read"
        user_message = result.hint or "The WeChat page loaded, but content is not ready yet."
    elif result.status == PageStatus.BROWSER_NOT_FOUND:
        next_action = "guide_browser_setup"
        user_message = result.hint or "No attachable browser was found. Run `wechat-reader setup`."
    elif result.status == PageStatus.BROWSER_NOT_READY:
        if "playwright is not installed" in hint_text:
            next_action = "install_dependencies"
        else:
            next_action = "guide_browser_setup"
        user_message = result.hint or "The browser bridge is not ready. Verify the local browser bridge and retry."
    elif result.status == PageStatus.UNSUPPORTED_PAGE:
        next_action = "fallback_non_wechat"
        user_message = result.hint or "The current page is not a supported WeChat article."
    elif result.status == PageStatus.NAVIGATION_FAILED:
        if "playwright is not installed" in hint_text:
            next_action = "install_dependencies"
        elif "run: wechat-reader setup" in hint_text or "no browser executable found" in hint_text:
            next_action = "guide_browser_setup"

    response: dict[str, Any] = {
        "tool": "wechat-reader",
        "status": result.status.value,
        "next_action": next_action,
        "user_message": user_message,
        "hint": result.hint,
        "page_title": result.page_title,
        "target_id": result.target_id,
        "raw_result": result.to_dict(),
    }
    if result.status == PageStatus.OK:
        response["article"] = _article_payload(result)
    return response


def openclaw_open_sync(url: str, **kwargs: Any) -> dict[str, Any]:
    return build_openclaw_response(open_article_sync(url, **kwargs))


def openclaw_read_sync(url: str, **kwargs: Any) -> dict[str, Any]:
    return build_openclaw_response(read_article_sync(url, **kwargs))
