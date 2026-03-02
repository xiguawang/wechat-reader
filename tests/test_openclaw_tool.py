import argparse
import unittest
from pathlib import Path

from wechat_reader.openclaw_tool import _command_kwargs


class OpenClawToolTests(unittest.TestCase):
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
