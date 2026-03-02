import unittest
from unittest.mock import patch

from wechat_reader.mcp_server import handle_message
from wechat_reader.models import ArticleResult, BrowserTab, PageStatus


class McpServerTests(unittest.TestCase):
    def test_initialize_returns_tools_capability(self) -> None:
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )

        assert response is not None
        self.assertEqual(response["result"]["capabilities"]["tools"]["listChanged"], False)
        self.assertEqual(response["result"]["capabilities"]["resources"]["listChanged"], False)
        self.assertEqual(response["result"]["serverInfo"]["name"], "mp-article-bridge")

    def test_tools_list_includes_expected_tool_names(self) -> None:
        response = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

        assert response is not None
        tools = response["result"]["tools"]
        tool_names = [tool["name"] for tool in tools]
        self.assertEqual(
            tool_names,
            [
                "wechat_read_article",
                "wechat_open_article",
                "wechat_list_tabs",
                "wechat_read_current_tab",
                "wechat_get_status",
                "wechat_setup",
            ],
        )
        self.assertIn("annotations", tools[0])
        self.assertIn("outputSchema", tools[0])
        self.assertEqual(tools[2]["annotations"]["readOnlyHint"], True)

    def test_resources_list_includes_runtime_and_doc_resources(self) -> None:
        response = handle_message({"jsonrpc": "2.0", "id": 21, "method": "resources/list", "params": {}})

        assert response is not None
        resources = response["result"]["resources"]
        uris = [resource["uri"] for resource in resources]
        self.assertIn("mp-article-bridge://setup", uris)
        self.assertIn("mp-article-bridge://tabs", uris)
        self.assertTrue(any(uri.endswith("/README.md") for uri in uris))

    def test_resources_read_returns_setup_json(self) -> None:
        with patch("wechat_reader.mcp_server.run_setup_diagnostics", return_value={"reachable_cdp": []}):
            response = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 22,
                    "method": "resources/read",
                    "params": {"uri": "mp-article-bridge://setup"},
                }
            )

        assert response is not None
        contents = response["result"]["contents"]
        self.assertEqual(contents[0]["mimeType"], "application/json")
        self.assertIn("reachable_cdp", contents[0]["text"])

    def test_resources_read_returns_tabs_json(self) -> None:
        tab = BrowserTab(id="tab-1", title="Example", url="https://mp.weixin.qq.com/s?...")
        with patch("wechat_reader.mcp_server.list_wechat_tabs_sync", return_value=[tab]):
            response = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 23,
                    "method": "resources/read",
                    "params": {"uri": "mp-article-bridge://tabs"},
                }
            )

        assert response is not None
        contents = response["result"]["contents"]
        self.assertIn("tab-1", contents[0]["text"])

    def test_resources_read_unknown_resource_returns_jsonrpc_error(self) -> None:
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 24,
                "method": "resources/read",
                "params": {"uri": "mp-article-bridge://missing"},
            }
        )

        assert response is not None
        self.assertEqual(response["error"]["code"], -32002)

    def test_wechat_read_article_returns_structured_content(self) -> None:
        result = ArticleResult(
            status=PageStatus.OK,
            url="https://mp.weixin.qq.com/s?...",
            title="Example",
            author="Author",
            content="Body",
        )

        with patch("wechat_reader.mcp_server.read_article_sync", return_value=result):
            response = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "wechat_read_article",
                        "arguments": {"url": "https://mp.weixin.qq.com/s?...", "strategy": "attach"},
                    },
                }
            )

        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["title"], "Example")
        self.assertFalse(response["result"]["isError"])

    def test_wechat_setup_returns_resource_link(self) -> None:
        with patch("wechat_reader.mcp_server.run_setup_diagnostics", return_value={"reachable_cdp": []}):
            response = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 32,
                    "method": "tools/call",
                    "params": {"name": "wechat_setup", "arguments": {}},
                }
            )

        assert response is not None
        resource_links = [item for item in response["result"]["content"] if item["type"] == "resource_link"]
        self.assertEqual(resource_links[0]["uri"], "mp-article-bridge://setup")

    def test_wechat_read_article_returns_tool_error_when_url_missing(self) -> None:
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {"name": "wechat_read_article", "arguments": {}},
            }
        )

        assert response is not None
        self.assertTrue(response["result"]["isError"])
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["error"]["code"], "missing_argument")
        self.assertEqual(payload["error"]["tool"], "wechat_read_article")

    def test_wechat_read_current_tab_uses_selected_tab_url(self) -> None:
        tab = BrowserTab(id="tab-1", title="Example", url="https://mp.weixin.qq.com/s?...")
        result = ArticleResult(
            status=PageStatus.OK,
            url=tab.url,
            title="Example",
            author="Author",
            content="Body",
        )

        with (
            patch("wechat_reader.mcp_server.list_wechat_tabs_sync", return_value=[tab]),
            patch("wechat_reader.mcp_server.read_article_sync", return_value=result) as read_article_sync,
        ):
            response = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "wechat_read_current_tab",
                        "arguments": {"tab_id": "tab-1", "strategy": "attach"},
                    },
                }
            )

        assert response is not None
        read_article_sync.assert_called_once()
        self.assertEqual(read_article_sync.call_args.args[0], tab.url)
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["selected_tab"]["id"], "tab-1")

    def test_wechat_get_status_uses_current_tab_when_url_missing(self) -> None:
        tab = BrowserTab(id="tab-1", title="Example", url="https://mp.weixin.qq.com/s?...")
        result = ArticleResult.status_only(PageStatus.CAPTCHA_REQUIRED, url=tab.url, hint="Verify first.")

        with (
            patch("wechat_reader.mcp_server.list_wechat_tabs_sync", return_value=[tab]),
            patch("wechat_reader.mcp_server.open_article_sync", return_value=result) as open_article_sync,
        ):
            response = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "wechat_get_status",
                        "arguments": {"strategy": "attach"},
                    },
                }
            )

        assert response is not None
        open_article_sync.assert_called_once()
        self.assertEqual(open_article_sync.call_args.args[0], tab.url)
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["status"], "captcha_required")
        self.assertEqual(payload["selected_tab"]["id"], "tab-1")

    def test_unknown_method_returns_jsonrpc_error(self) -> None:
        response = handle_message({"jsonrpc": "2.0", "id": 6, "method": "unknown/method", "params": {}})

        assert response is not None
        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_tool_returns_tool_error_payload(self) -> None:
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "unknown_tool", "arguments": {}},
            }
        )

        assert response is not None
        self.assertTrue(response["result"]["isError"])
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["error"]["code"], "unknown_tool")
        self.assertEqual(payload["error"]["tool"], "unknown_tool")


if __name__ == "__main__":
    unittest.main()
