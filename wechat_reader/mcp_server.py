"""Minimal stdio MCP server for mp-article-bridge."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .browser_bridge import list_wechat_tabs_sync, open_article_sync, read_article_sync
from .models import ArticleResult, BrowserTab, PageStatus
from .setup import run_setup_diagnostics

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "mp-article-bridge"


def _server_version() -> str:
    try:
        return version("mp-article-bridge")
    except PackageNotFoundError:
        return "0.1.0"


def _jsonrpc_response(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": message_id, "result": result}


def _jsonrpc_error(message_id: Any, code: int, message: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": message_id, "error": payload}


def _text_tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": is_error,
    }


def _tool_error_payload(message: str, *, code: str, tool_name: str) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "tool": tool_name,
        }
    }


def _article_result_payload(result: ArticleResult) -> dict[str, Any]:
    return result.to_dict()


def _tabs_payload(tabs: list[BrowserTab]) -> dict[str, Any]:
    return {"tabs": [tab.to_dict() for tab in tabs]}


def _coerce_browser_kwargs(arguments: dict[str, Any]) -> dict[str, Any]:
    profile_dir = arguments.get("profile_dir")
    kwargs: dict[str, Any] = {
        "strategy": arguments.get("strategy", "auto"),
        "cdp_url": arguments.get("cdp_url"),
        "timeout": int(arguments.get("timeout", 30)),
        "wait_for_manual_verify": int(arguments.get("wait_for_manual_verify", 0)),
        "channel": arguments.get("channel", "chrome"),
        "profile_dir": Path(profile_dir) if isinstance(profile_dir, str) and profile_dir else None,
        "profile_name": arguments.get("profile_name", "default"),
        "ephemeral": bool(arguments.get("ephemeral", False)),
    }
    return kwargs


def _resolve_current_tab(arguments: dict[str, Any]) -> BrowserTab | None:
    tabs = list_wechat_tabs_sync(arguments.get("cdp_url"), wechat_only=True)
    tab_id = arguments.get("tab_id")
    if isinstance(tab_id, str) and tab_id:
        for tab in tabs:
            if tab.id == tab_id:
                return tab
        return None
    return tabs[0] if tabs else None


def _tool_definitions() -> list[dict[str, Any]]:
    browser_properties = {
        "strategy": {
            "type": "string",
            "enum": ["auto", "attach", "launch", "playwright"],
            "description": "Browser connection strategy.",
        },
        "cdp_url": {"type": "string", "description": "Explicit Chrome DevTools Protocol endpoint."},
        "timeout": {"type": "integer", "minimum": 1, "description": "Timeout in seconds."},
        "wait_for_manual_verify": {
            "type": "integer",
            "minimum": 0,
            "description": "Seconds to wait for manual WeChat verification before returning.",
        },
        "channel": {
            "type": "string",
            "enum": ["chrome", "chromium"],
            "description": "Browser family to launch when launch mode is used.",
        },
        "profile_dir": {"type": "string", "description": "Explicit profile directory for launch/playwright modes."},
        "profile_name": {"type": "string", "description": "Named profile under the default profile root."},
        "ephemeral": {"type": "boolean", "description": "Use a temporary profile instead of the persistent one."},
    }
    article_output_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "url": {"type": "string"},
            "title": {"type": "string"},
            "author": {"type": "string"},
            "content": {"type": "string"},
            "publish_time": {"type": ["string", "null"]},
            "account_name": {"type": ["string", "null"]},
            "fetched_at": {"type": ["string", "null"]},
            "hint": {"type": ["string", "null"]},
            "page_title": {"type": ["string", "null"]},
            "metadata": {"type": "object"},
        },
        "required": ["status", "url", "metadata"],
    }
    tabs_output_schema = {
        "type": "object",
        "properties": {
            "tabs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": ["string", "null"]},
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "kind": {"type": "string"},
                        "profile": {"type": ["string", "null"]},
                    },
                    "required": ["title", "url", "kind"],
                },
            }
        },
        "required": ["tabs"],
    }
    setup_output_schema = {
        "type": "object",
        "properties": {"setup": {"type": "object"}},
        "required": ["setup"],
    }
    return [
        {
            "name": "wechat_read_article",
            "title": "Read WeChat Article",
            "description": "Read a WeChat article URL through the local browser bridge and return structured article data or status.",
            "annotations": {
                "title": "Read WeChat Article",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "WeChat article URL or captcha wrapper URL."},
                    **browser_properties,
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            "outputSchema": article_output_schema,
        },
        {
            "name": "wechat_open_article",
            "title": "Open WeChat Article",
            "description": "Open a WeChat article URL and return structured page status without requiring full extraction.",
            "annotations": {
                "title": "Open WeChat Article",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "WeChat article URL or captcha wrapper URL."},
                    **browser_properties,
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            "outputSchema": article_output_schema,
        },
        {
            "name": "wechat_list_tabs",
            "title": "List WeChat Tabs",
            "description": "List attachable browser tabs, filtered to WeChat tabs by default.",
            "annotations": {
                "title": "List WeChat Tabs",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "cdp_url": {"type": "string", "description": "Explicit Chrome DevTools Protocol endpoint."},
                    "wechat_only": {
                        "type": "boolean",
                        "description": "When true, only return WeChat tabs.",
                        "default": True,
                    },
                },
                "additionalProperties": False,
            },
            "outputSchema": tabs_output_schema,
        },
        {
            "name": "wechat_read_current_tab",
            "title": "Read Current WeChat Tab",
            "description": "Read the first attachable WeChat tab, or a specific tab by tab_id.",
            "annotations": {
                "title": "Read Current WeChat Tab",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "string", "description": "Optional specific tab id from wechat_list_tabs."},
                    **browser_properties,
                },
                "additionalProperties": False,
            },
            "outputSchema": article_output_schema,
        },
        {
            "name": "wechat_get_status",
            "title": "Get WeChat Page Status",
            "description": "Inspect the current status of a WeChat article URL or the current WeChat tab without requiring a full successful read.",
            "annotations": {
                "title": "Get WeChat Page Status",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Optional WeChat article URL. If omitted, inspect the current WeChat tab."},
                    "tab_id": {"type": "string", "description": "Optional specific tab id from wechat_list_tabs."},
                    **browser_properties,
                },
                "additionalProperties": False,
            },
            "outputSchema": article_output_schema,
        },
        {
            "name": "wechat_setup",
            "title": "Diagnose Bridge Setup",
            "description": "Return local browser bridge diagnostics and setup guidance.",
            "annotations": {
                "title": "Diagnose Bridge Setup",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
            "inputSchema": {"type": "object", "additionalProperties": False},
            "outputSchema": setup_output_schema,
        },
    ]


def _handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "wechat_read_article":
        url = arguments.get("url")
        if not isinstance(url, str) or not url.strip():
            return _text_tool_result(
                _tool_error_payload("url is required", code="missing_argument", tool_name=name),
                is_error=True,
            )
        return _text_tool_result(_article_result_payload(read_article_sync(url, **_coerce_browser_kwargs(arguments))))

    if name == "wechat_open_article":
        url = arguments.get("url")
        if not isinstance(url, str) or not url.strip():
            return _text_tool_result(
                _tool_error_payload("url is required", code="missing_argument", tool_name=name),
                is_error=True,
            )
        return _text_tool_result(_article_result_payload(open_article_sync(url, **_coerce_browser_kwargs(arguments))))

    if name == "wechat_list_tabs":
        tabs = list_wechat_tabs_sync(
            arguments.get("cdp_url"),
            wechat_only=bool(arguments.get("wechat_only", True)),
        )
        return _text_tool_result(_tabs_payload(tabs))

    if name == "wechat_read_current_tab":
        tab = _resolve_current_tab(arguments)
        if tab is None:
            result = ArticleResult.status_only(
                PageStatus.BROWSER_NOT_FOUND,
                url="",
                hint="No attachable WeChat tab was found.",
            )
            return _text_tool_result(_article_result_payload(result))
        payload = _article_result_payload(read_article_sync(tab.url, **_coerce_browser_kwargs(arguments)))
        payload["selected_tab"] = asdict(tab)
        return _text_tool_result(payload)

    if name == "wechat_get_status":
        url = arguments.get("url")
        selected_tab: BrowserTab | None = None
        if not isinstance(url, str) or not url.strip():
            selected_tab = _resolve_current_tab(arguments)
            if selected_tab is None:
                result = ArticleResult.status_only(
                    PageStatus.BROWSER_NOT_FOUND,
                    url="",
                    hint="No attachable WeChat tab was found.",
                )
                return _text_tool_result(_article_result_payload(result))
            url = selected_tab.url
        payload = _article_result_payload(open_article_sync(url, **_coerce_browser_kwargs(arguments)))
        if selected_tab is not None:
            payload["selected_tab"] = asdict(selected_tab)
        return _text_tool_result(payload)

    if name == "wechat_setup":
        return _text_tool_result({"setup": run_setup_diagnostics()})

    return _text_tool_result(
        _tool_error_payload(f"Unknown tool: {name}", code="unknown_tool", tool_name=name),
        is_error=True,
    )


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _jsonrpc_error(message_id, -32602, "params must be an object")

    if method == "initialize":
        requested_version = params.get("protocolVersion")
        if requested_version and not isinstance(requested_version, str):
            return _jsonrpc_error(message_id, -32602, "protocolVersion must be a string")
        return _jsonrpc_response(
            message_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "title": "mp-article-bridge MCP Server",
                    "version": _server_version(),
                },
                "instructions": "Use the WeChat bridge tools to inspect WeChat tabs, read verified articles, and diagnose local bridge setup.",
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return _jsonrpc_response(message_id, {})

    if method == "tools/list":
        return _jsonrpc_response(message_id, {"tools": _tool_definitions()})

    if method == "tools/call":
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            return _jsonrpc_error(message_id, -32602, "tools/call requires a tool name")
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _jsonrpc_error(message_id, -32602, "tool arguments must be an object")
        return _jsonrpc_response(message_id, _handle_tool_call(tool_name, arguments))

    if method and method.startswith("notifications/"):
        return None

    return _jsonrpc_error(message_id, -32601, f"Method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            response = _jsonrpc_error(None, -32700, "Parse error")
        else:
            if not isinstance(message, dict):
                response = _jsonrpc_error(None, -32600, "Invalid Request")
            else:
                response = handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
