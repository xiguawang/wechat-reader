import unittest

from wechat_reader.models import PageStatus
from wechat_reader.wechat_parser import classify_page, payload_to_result, wait_for_article_result


class ParserTests(unittest.TestCase):
    def test_classify_page_detects_captcha_when_manual_verification_is_possible(self) -> None:
        status, hint = classify_page(
            "https://mp.weixin.qq.com/s/example",
            {"body_text": "环境异常 当前环境异常，完成验证后即可继续访问。", "page_title": "微信公众平台"},
        )

        self.assertEqual(status, PageStatus.CAPTCHA_REQUIRED)
        self.assertIn("环境异常", hint or "")

    def test_classify_page_detects_rate_limited_state(self) -> None:
        status, hint = classify_page(
            "https://mp.weixin.qq.com/s/example",
            {"body_text": "操作频繁，请稍后再试。", "page_title": "微信公众平台"},
        )

        self.assertEqual(status, PageStatus.RATE_LIMITED)
        self.assertIn("操作频繁", hint or "")

    def test_payload_to_result_returns_ok_when_content_exists(self) -> None:
        result = payload_to_result(
            "https://mp.weixin.qq.com/s/example",
            {
                "title": "Title",
                "author": "Author",
                "account_name": "Account",
                "content": "Body",
                "html": "<p>Body</p>",
                "publish_time": "2026-03-01",
                "page_title": "Title",
            },
        )

        self.assertEqual(result.status, PageStatus.OK)
        self.assertEqual(result.content, "Body")
        self.assertEqual(result.author, "Author")

    def test_wait_for_article_result_returns_navigation_failed_when_title_lookup_breaks(self) -> None:
        class PlaywrightError(Exception):
            pass

        class FakePage:
            url = "https://mp.weixin.qq.com/s/example"

            def evaluate(self, script: str) -> dict[str, str]:
                return {"content": "", "body_text": "", "page_title": ""}

            def title(self) -> str:
                raise PlaywrightError("title lookup failed")

        result = wait_for_article_result(FakePage(), 0, PlaywrightError)

        self.assertEqual(result.status, PageStatus.NAVIGATION_FAILED)
        self.assertIn("title lookup failed", result.hint or "")


if __name__ == "__main__":
    unittest.main()
