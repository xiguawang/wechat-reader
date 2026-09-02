import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from wechat_reader.cli import main
from wechat_reader.models import ArticleResult, BrowserTab, PageStatus


class _RecordingTextStream:
    """Fake console stream: records reconfigure() calls and encodes writes with
    its current settings, so an unreconfigured cp936 stream raises
    UnicodeEncodeError exactly like a real Chinese Windows terminal."""

    def __init__(self, encoding: str = "cp936", errors: str = "strict") -> None:
        self.encoding = encoding
        self._errors = errors
        self._buffer = io.BytesIO()
        self.reconfigure_calls: list[dict[str, str | None]] = []

    def reconfigure(self, *, encoding: str | None = None, errors: str | None = None) -> None:
        self.reconfigure_calls.append({"encoding": encoding, "errors": errors})
        if encoding is not None:
            self.encoding = encoding
        if errors is not None:
            self._errors = errors

    def write(self, text: str) -> int:
        data = text.encode(self.encoding, self._errors)
        self._buffer.write(data)
        return len(data)

    def flush(self) -> None:
        pass

    def getvalue(self) -> str:
        return self._buffer.getvalue().decode(self.encoding, "replace")


class CliTests(unittest.TestCase):
    def test_read_json_returns_zero_for_ok_result(self) -> None:
        result = ArticleResult(
            status=PageStatus.OK,
            url="https://mp.weixin.qq.com/s?...",
            title="Example",
            author="Author",
            content="Body",
            fetched_at="2026-03-02T00:00:00Z",
        )
        stdout = io.StringIO()

        with (
            patch("wechat_reader.cli.read_article_sync", return_value=result),
            redirect_stdout(stdout),
        ):
            exit_code = main(["read", "https://mp.weixin.qq.com/s?...", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["title"], "Example")

    def test_read_returns_nonzero_for_blocked_result(self) -> None:
        result = ArticleResult.status_only(
            PageStatus.CAPTCHA_REQUIRED,
            url="https://mp.weixin.qq.com/s?...",
            hint="Please complete verification in the browser, then retry.",
        )
        stdout = io.StringIO()

        with (
            patch("wechat_reader.cli.read_article_sync", return_value=result),
            redirect_stdout(stdout),
        ):
            exit_code = main(["read", "https://mp.weixin.qq.com/s?...", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "captcha_required")

    def test_read_with_output_saves_markdown_on_success(self) -> None:
        result = ArticleResult(
            status=PageStatus.OK,
            url="https://mp.weixin.qq.com/s?...",
            title="Example",
            author="Author",
            content="Body",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            save_path = output_dir / "Example.md"

            with (
                patch("wechat_reader.cli.read_article_sync", return_value=result),
                patch("wechat_reader.cli.save_markdown", return_value=save_path) as save_markdown,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(["read", "https://mp.weixin.qq.com/s?...", "--output", str(output_dir)])

        self.assertEqual(exit_code, 0)
        save_markdown.assert_called_once_with(result, output_dir)
        self.assertIn("Saved:", stderr.getvalue())

    def test_tabs_plaintext_outputs_one_line_per_tab(self) -> None:
        tabs = [BrowserTab(id="tab-1", title="Example", url="https://mp.weixin.qq.com/s?...")]
        stdout = io.StringIO()

        with (
            patch("wechat_reader.cli.list_wechat_tabs_sync", return_value=tabs),
            redirect_stdout(stdout),
        ):
            exit_code = main(["tabs", "--wechat-only"])

        self.assertEqual(exit_code, 0)
        self.assertIn("tab-1\tExample\thttps://mp.weixin.qq.com/s?...", stdout.getvalue())

    def test_setup_json_outputs_report(self) -> None:
        report = {"reachable_cdp": [], "default_profile_dir": "/tmp/profile"}
        stdout = io.StringIO()

        with (
            patch("wechat_reader.cli.run_setup_diagnostics", return_value=report),
            redirect_stdout(stdout),
        ):
            exit_code = main(["setup", "--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), report)


    def test_read_on_windows_reconfigures_streams_to_utf8(self) -> None:
        result = ArticleResult(
            status=PageStatus.OK,
            url="https://mp.weixin.qq.com/s?...",
            title="标题\xa0含\U0001f642emoji",
            author="作者",
            content="正文\xa0测试",
            fetched_at="2026-03-02T00:00:00Z",
        )
        stdout = _RecordingTextStream()
        stderr = _RecordingTextStream()

        with (
            patch.object(sys, "platform", "win32"),
            patch("wechat_reader.cli.read_article_sync", return_value=result),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = main(["read", "https://mp.weixin.qq.com/s?..."])

        self.assertEqual(exit_code, 0)
        expected_calls = [{"encoding": "utf-8", "errors": "replace"}]
        self.assertEqual(stdout.reconfigure_calls, expected_calls)
        self.assertEqual(stderr.reconfigure_calls, expected_calls)
        output = stdout.getvalue()
        self.assertIn("正文\xa0测试", output)
        self.assertIn("\U0001f642", output)

    def test_read_off_windows_keeps_user_stream_encoding(self) -> None:
        result = ArticleResult(
            status=PageStatus.OK,
            url="https://mp.weixin.qq.com/s?...",
            title="Example",
            author="Author",
            content="Body \xa0 with user-chosen utf-8 stream",
            fetched_at="2026-03-02T00:00:00Z",
        )
        stdout = _RecordingTextStream(encoding="utf-8")

        with (
            patch.object(sys, "platform", "darwin"),
            patch("wechat_reader.cli.read_article_sync", return_value=result),
            redirect_stdout(stdout),
        ):
            exit_code = main(["read", "https://mp.weixin.qq.com/s?..."])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.reconfigure_calls, [])


if __name__ == "__main__":
    unittest.main()
