import unittest

from wechat_reader.integrations.openclaw import build_openclaw_response
from wechat_reader.models import ArticleResult, PageStatus


class OpenClawTests(unittest.TestCase):
    def test_build_openclaw_response_for_ok(self) -> None:
        result = ArticleResult(
            status=PageStatus.OK,
            url="https://mp.weixin.qq.com/s?...",
            title="Example",
            author="Author",
            content="Body",
            fetched_at="2026-03-02T00:00:00Z",
        )

        payload = build_openclaw_response(result)

        self.assertEqual(payload["next_action"], "return_article")
        self.assertEqual(payload["article"]["title"], "Example")

    def test_build_openclaw_response_for_captcha(self) -> None:
        result = ArticleResult.status_only(
            PageStatus.CAPTCHA_REQUIRED,
            url="https://mp.weixin.qq.com/s?...",
            hint="Please complete verification in the browser, then retry.",
        )

        payload = build_openclaw_response(result)

        self.assertEqual(payload["next_action"], "ask_user_to_verify")
        self.assertIn("verification", payload["user_message"].lower())

    def test_build_openclaw_response_for_missing_playwright(self) -> None:
        result = ArticleResult.status_only(
            PageStatus.NAVIGATION_FAILED,
            url="https://mp.weixin.qq.com/s?...",
            hint="Playwright is not installed. Run: pip install playwright && playwright install chromium",
        )

        payload = build_openclaw_response(result)

        self.assertEqual(payload["next_action"], "install_dependencies")

    def test_build_openclaw_response_for_browser_not_ready(self) -> None:
        result = ArticleResult.status_only(
            PageStatus.BROWSER_NOT_READY,
            url="https://mp.weixin.qq.com/s?...",
            hint="Failed to connect to existing browser via CDP: connect EPERM 127.0.0.1:9222",
        )

        payload = build_openclaw_response(result)

        self.assertEqual(payload["next_action"], "guide_browser_setup")
