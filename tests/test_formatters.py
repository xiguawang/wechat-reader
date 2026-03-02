import unittest

from wechat_reader.formatters import article_to_markdown
from wechat_reader.models import ArticleResult, PageStatus


class FormatterTests(unittest.TestCase):
    def test_article_to_markdown_includes_hint_for_non_ok_status(self) -> None:
        result = ArticleResult(
            status=PageStatus.CAPTCHA_REQUIRED,
            url="https://mp.weixin.qq.com/s/example",
            title="Blocked",
            hint="Please verify in browser.",
        )

        markdown = article_to_markdown(result)

        self.assertIn("- Status: captcha_required", markdown)
        self.assertIn("- Hint: Please verify in browser.", markdown)


if __name__ == "__main__":
    unittest.main()
