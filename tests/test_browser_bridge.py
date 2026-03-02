import unittest
from unittest.mock import patch

from wechat_reader.browser_bridge import BridgeError, read_article_sync, unwrap_wechat_article_url
from wechat_reader.models import ArticleResult, PageStatus, Strategy


class BrowserBridgeTests(unittest.TestCase):
    def test_unwrap_wechat_article_url_carries_target_url_and_poc_token(self) -> None:
        wrapper_url = (
            "https://mp.weixin.qq.com/mp/wappoc_appmsgcaptcha?"
            "poc_token=abc123&target_url=https%3A%2F%2Fmp.weixin.qq.com%2Fs%3Fmid%3D1%26idx%3D1"
        )

        result = unwrap_wechat_article_url(wrapper_url)

        self.assertEqual(result, "https://mp.weixin.qq.com/s?mid=1&idx=1&poc_token=abc123")

    def test_read_article_returns_browser_not_ready_for_missing_playwright(self) -> None:
        with patch(
            "wechat_reader.browser_bridge.open_runtime",
            side_effect=BridgeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ),
        ):
            result = read_article_sync("https://mp.weixin.qq.com/s/example", strategy="attach")

        self.assertEqual(result.status, PageStatus.BROWSER_NOT_READY)
        self.assertIn("Playwright is not installed", result.hint or "")
        self.assertEqual(result.metadata["requested_url"], "https://mp.weixin.qq.com/s/example")
        self.assertEqual(result.metadata["effective_url"], "https://mp.weixin.qq.com/s/example")
        self.assertFalse(result.metadata["url_unwrapped"])

    def test_read_article_reuses_unwrapped_target_url_without_returning_to_captcha(self) -> None:
        wrapper_url = (
            "https://mp.weixin.qq.com/mp/wappoc_appmsgcaptcha?"
            "poc_token=abc123&target_url=https%3A%2F%2Fmp.weixin.qq.com%2Fs%3Fmid%3D1%26idx%3D1"
        )
        article_url = "https://mp.weixin.qq.com/s?mid=1&idx=1&poc_token=abc123"

        class FakePage:
            def __init__(self) -> None:
                self.url = article_url
                self.goto_calls = 0

            def goto(self, *args, **kwargs) -> None:
                self.goto_calls += 1

            def wait_for_load_state(self, *args, **kwargs) -> None:
                return None

        class FakeContext:
            def __init__(self, page: FakePage) -> None:
                self.pages = [page]

            def new_page(self) -> FakePage:
                raise AssertionError("new_page should not be used when the article tab already exists")

        class FakeRuntime:
            def __init__(self, page: FakePage) -> None:
                self.context = FakeContext(page)
                self.strategy = Strategy.ATTACH
                self.cdp_url = "http://127.0.0.1:9222"

            def close(self) -> None:
                return None

        page = FakePage()

        with (
            patch("wechat_reader.browser_bridge.open_runtime", return_value=FakeRuntime(page)),
            patch("wechat_reader.browser_bridge.load_playwright", return_value=(object(), TimeoutError, Exception)),
            patch(
                "wechat_reader.browser_bridge.wait_for_article_result",
                return_value=ArticleResult(
                    status=PageStatus.OK,
                    url=article_url,
                    title="Example",
                    author="Author",
                    content="Body",
                ),
            ),
        ):
            result = read_article_sync(wrapper_url, strategy="attach", cdp_url="http://127.0.0.1:9222")

        self.assertEqual(result.status, PageStatus.OK)
        self.assertEqual(page.goto_calls, 0)
        self.assertEqual(result.metadata["requested_url"], wrapper_url)
        self.assertEqual(result.metadata["effective_url"], article_url)
        self.assertTrue(result.metadata["url_unwrapped"])
        self.assertTrue(result.metadata["reused_existing_tab"])
        self.assertFalse(result.metadata["navigation_performed"])
        self.assertEqual(result.metadata["runtime_strategy"], "attach")


if __name__ == "__main__":
    unittest.main()
