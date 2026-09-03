import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.helpers import _RecordingTextStream
from wechat_reader.openclaw_tool import _command_kwargs, main


class OpenClawToolTests(unittest.TestCase):
    def test_main_on_windows_reconfigures_all_stdio_streams(self) -> None:
        stdin = _RecordingTextStream()
        stdout = _RecordingTextStream()
        stderr = _RecordingTextStream()

        with (
            patch.object(sys, "platform", "win32"),
            patch.object(sys, "stdin", stdin),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
        ):
            exit_code = main(["schema"])

        self.assertEqual(exit_code, 0)
        expected_calls = [{"encoding": "utf-8", "errors": "replace"}]
        self.assertEqual(stdin.reconfigure_calls, expected_calls)
        self.assertEqual(stdout.reconfigure_calls, expected_calls)
        self.assertEqual(stderr.reconfigure_calls, expected_calls)

    def test_main_off_windows_keeps_user_stream_encoding(self) -> None:
        stdin = _RecordingTextStream()
        stdout = _RecordingTextStream(encoding="utf-8")
        stderr = _RecordingTextStream(encoding="utf-8")

        with (
            patch.object(sys, "platform", "darwin"),
            patch.object(sys, "stdin", stdin),
            patch.object(sys, "stdout", stdout),
            patch.object(sys, "stderr", stderr),
        ):
            exit_code = main(["schema"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdin.reconfigure_calls, [])
        self.assertEqual(stdout.reconfigure_calls, [])
        self.assertEqual(stderr.reconfigure_calls, [])

    def test_command_kwargs_prefers_stdin_payload_over_defaults(self) -> None:
        args = argparse.Namespace(
            url=None,
            strategy="launch",
            cdp_url=None,
            timeout=30,
            wait_for_manual_verify=90,
            channel="chrome",
            profile_dir=None,
            profile_name="default",
            ephemeral=False,
        )

        url, kwargs = _command_kwargs(
            args,
            {
                "url": "https://mp.weixin.qq.com/s?...",
                "strategy": "attach",
                "timeout": 12,
                "wait_for_manual_verify": 45,
                "profile_dir": "/tmp/wechat-profile",
            },
        )

        self.assertEqual(url, "https://mp.weixin.qq.com/s?...")
        self.assertEqual(kwargs["strategy"], "attach")
        self.assertEqual(kwargs["timeout"], 12)
        self.assertEqual(kwargs["wait_for_manual_verify"], 45)
        self.assertEqual(kwargs["profile_dir"], Path("/tmp/wechat-profile"))
