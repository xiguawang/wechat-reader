"""Browser bridge and WeChat article access helpers."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen

from .models import ArticleResult, BrowserTab, PageStatus, Strategy
from .wechat_parser import wait_for_article_result, wait_for_manual_resolution

DEFAULT_TIMEOUT_SECONDS = 30
NETWORK_IDLE_TIMEOUT_MS = 10_000
COMMON_CDP_URLS = tuple(f"http://127.0.0.1:{port}" for port in range(9222, 9236)) + tuple(
    f"http://localhost:{port}" for port in range(9222, 9236)
)


class BridgeError(RuntimeError):
    """Raised when the browser bridge cannot satisfy the request."""


@dataclass(slots=True)
class BrowserRuntime:
    playwright_manager: Any
    browser: Any | None
    context: Any
    strategy: Strategy
    cdp_url: str | None = None
    close_context: bool = True
    close_browser: bool = True

    def close(self) -> None:
        try:
            if self.close_context:
                self.context.close()
        finally:
            if self.browser is not None and self.close_browser:
                try:
                    self.browser.close()
                except Exception:  # noqa: BLE001
                    pass
            if self.playwright_manager is not None:
                self.playwright_manager.stop()


@dataclass(slots=True)
class PageMatch:
    page: Any
    target_id: str | None = None
    reused_existing_tab: bool = False


def load_playwright() -> tuple[Any, type[BaseException], type[BaseException]]:
    try:
        from playwright.sync_api import Error, TimeoutError, sync_playwright
    except ModuleNotFoundError as exc:
        raise BridgeError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc
    return sync_playwright, TimeoutError, Error


def default_profile_root(profile_name: str = "default") -> Path:
    return Path.home() / ".wechat-reader" / "profiles" / profile_name


def bridge_metadata_path(profile_dir: Path) -> Path:
    return profile_dir / "wechat-reader.json"


def bridge_profiles_root() -> Path:
    return Path.home() / ".wechat-reader" / "profiles"


def browser_executable_candidates() -> list[str]:
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    return [candidate for candidate in candidates if candidate and Path(candidate).exists()]


def browser_executable_for_channel(channel: str) -> str | None:
    ordered = browser_executable_candidates()
    if channel == "chrome":
        for candidate in ordered:
            if "Google Chrome" in candidate or candidate.endswith("google-chrome"):
                return candidate
    if channel == "chromium":
        for candidate in ordered:
            if "Chromium" in candidate or candidate.endswith("chromium") or candidate.endswith("chromium-browser"):
                return candidate
    return ordered[0] if ordered else None


def probe_cdp_endpoint(base_url: str, timeout_seconds: float = 1.0) -> dict[str, Any] | None:
    endpoint = base_url.rstrip("/") + "/json/version"
    try:
        with urlopen(endpoint, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except (URLError, OSError, TimeoutError):
        return None

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def discover_cdp_url() -> str | None:
    for candidate in discover_managed_cdp_urls():
        if probe_cdp_endpoint(candidate):
            return candidate
    for candidate in COMMON_CDP_URLS:
        if probe_cdp_endpoint(candidate):
            return candidate
    return None


def unwrap_wechat_article_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.netloc.lower() != "mp.weixin.qq.com" or "wappoc_appmsgcaptcha" not in parsed.path:
        return url

    wrapper_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    target_url = wrapper_params.get("target_url")
    if not target_url:
        return url

    target_parts = urlsplit(target_url)
    if not target_parts.scheme or not target_parts.netloc:
        return url

    target_params = dict(parse_qsl(target_parts.query, keep_blank_values=True))
    poc_token = wrapper_params.get("poc_token")
    if poc_token and "poc_token" not in target_params:
        target_params["poc_token"] = poc_token

    return urlunsplit(
        (
            target_parts.scheme,
            target_parts.netloc,
            target_parts.path,
            urlencode(target_params, doseq=True),
            target_parts.fragment,
        )
    )


def list_wechat_tabs_sync(cdp_url: str | None = None, *, wechat_only: bool = False) -> list[BrowserTab]:
    base_url = cdp_url or discover_cdp_url()
    if not base_url:
        return []

    endpoint = base_url.rstrip("/") + "/json/list"
    try:
        with urlopen(endpoint, timeout=1.5) as response:
            raw_tabs = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, TimeoutError, json.JSONDecodeError):
        return []

    tabs: list[BrowserTab] = []
    for item in raw_tabs:
        url = item.get("url", "") or ""
        if wechat_only and "mp.weixin.qq.com" not in url:
            continue
        tabs.append(
            BrowserTab(
                id=item.get("id"),
                title=item.get("title", "") or "",
                url=url,
                kind=item.get("type", "page") or "page",
                profile="attach",
            )
        )
    return tabs


async def list_wechat_tabs(cdp_url: str | None = None, *, wechat_only: bool = False) -> list[BrowserTab]:
    return await asyncio.to_thread(list_wechat_tabs_sync, cdp_url, wechat_only=wechat_only)


def normalize_strategy(value: Strategy | str | None) -> Strategy:
    if value is None:
        return Strategy.AUTO
    if isinstance(value, Strategy):
        return value
    return Strategy(value)


def _is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def find_available_port(start: int = 9222, end: int = 9235) -> int:
    for port in range(start, end + 1):
        if not _is_port_open(port):
            return port
    raise BridgeError("No available CDP port found in 9222-9235.")


def wait_for_cdp_url(base_url: str, timeout_seconds: float = 10.0) -> str | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        parsed = urlsplit(base_url)
        if parsed.port and _is_port_open(parsed.port) and probe_cdp_endpoint(base_url):
            return base_url
        time.sleep(0.25)
    return None


def read_bridge_metadata(profile_dir: Path) -> dict[str, Any] | None:
    metadata_path = bridge_metadata_path(profile_dir)
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def discover_managed_cdp_urls() -> list[str]:
    root = bridge_profiles_root()
    if not root.exists():
        return []

    urls: list[str] = []
    for metadata_path in root.glob("*/wechat-reader.json"):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cdp_url = payload.get("cdp_url")
        if isinstance(cdp_url, str) and cdp_url not in urls:
            urls.append(cdp_url)
    return urls


def discover_running_bridge_cdp_url(profile_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "aux"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    needle = str(profile_dir)
    for line in result.stdout.splitlines():
        if needle not in line or "--remote-debugging-port=" not in line:
            continue
        match = re.search(r"--remote-debugging-port=(\d+)", line)
        if not match:
            continue
        candidate = f"http://127.0.0.1:{match.group(1)}"
        if probe_cdp_endpoint(candidate, timeout_seconds=0.5):
            return candidate
    return None


def write_bridge_metadata(profile_dir: Path, *, cdp_url: str, channel: str) -> None:
    metadata_path = bridge_metadata_path(profile_dir)
    metadata_path.write_text(
        json.dumps({"cdp_url": cdp_url, "channel": channel}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _connect_attach_runtime(
    playwright_manager: Any,
    playwright_error: type[BaseException],
    *,
    cdp_url: str | None,
) -> BrowserRuntime:
    effective_cdp_url = cdp_url or discover_cdp_url()
    if not effective_cdp_url:
        raise BridgeError("No attachable browser found. Run: wechat-reader setup")
    deadline = time.monotonic() + 10.0
    last_error: Exception | None = None
    browser = None
    while time.monotonic() < deadline:
        try:
            browser = playwright_manager.chromium.connect_over_cdp(effective_cdp_url)
            break
        except playwright_error as exc:
            last_error = exc
            time.sleep(0.25)
    if browser is None:
        raise BridgeError(f"Failed to connect to existing browser via CDP: {last_error}") from last_error
    if browser.contexts:
        context = browser.contexts[0]
        close_context = False
    else:
        context = browser.new_context()
        close_context = True
    return BrowserRuntime(
        playwright_manager=None,
        browser=browser,
        context=context,
        strategy=Strategy.ATTACH,
        cdp_url=effective_cdp_url,
        close_context=close_context,
        close_browser=False,
    )


def _launch_persistent_runtime(
    playwright_manager: Any,
    playwright_error: type[BaseException],
    *,
    channel: str,
    profile_dir: Path,
    headless: bool,
) -> BrowserRuntime:
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        context = playwright_manager.chromium.launch_persistent_context(
            str(profile_dir),
            channel=None if channel == "chromium" else channel,
            headless=headless,
        )
    except playwright_error as exc:
        raise BridgeError(f"Failed to launch persistent browser context: {exc}") from exc
    return BrowserRuntime(
        playwright_manager=None,
        browser=None,
        context=context,
        strategy=Strategy.LAUNCH,
        close_context=True,
        close_browser=False,
    )


def _launch_managed_browser_process(*, channel: str, profile_dir: Path) -> str:
    executable = browser_executable_for_channel(channel)
    if not executable:
        raise BridgeError(f"No browser executable found for channel '{channel}'. Run: wechat-reader setup")

    profile_dir.mkdir(parents=True, exist_ok=True)
    running_cdp_url = discover_running_bridge_cdp_url(profile_dir)
    if running_cdp_url:
        write_bridge_metadata(profile_dir, cdp_url=running_cdp_url, channel=channel)
        return running_cdp_url

    existing = read_bridge_metadata(profile_dir)
    if existing:
        existing_cdp_url = existing.get("cdp_url")
        if isinstance(existing_cdp_url, str) and probe_cdp_endpoint(existing_cdp_url, timeout_seconds=0.5):
            return existing_cdp_url

    port = find_available_port()
    subprocess.Popen(
        [
            executable,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    launched_url = f"http://127.0.0.1:{port}"
    write_bridge_metadata(profile_dir, cdp_url=launched_url, channel=channel)
    if not wait_for_cdp_url(launched_url, timeout_seconds=20.0):
        raise BridgeError("Launched browser did not expose a CDP endpoint in time.")
    return launched_url


def open_runtime(
    *,
    strategy: Strategy | str = Strategy.AUTO,
    cdp_url: str | None = None,
    channel: str = "chrome",
    profile_dir: Path | None = None,
    profile_name: str = "default",
    ephemeral: bool = False,
    headless: bool = False,
) -> BrowserRuntime:
    strategy_value = normalize_strategy(strategy)
    sync_playwright, _, playwright_error = load_playwright()
    manager = sync_playwright().start()

    try:
        if strategy_value in {Strategy.AUTO, Strategy.ATTACH}:
            try:
                runtime = _connect_attach_runtime(manager, playwright_error, cdp_url=cdp_url)
            except BridgeError:
                if strategy_value == Strategy.ATTACH:
                    raise
            else:
                runtime.playwright_manager = manager
                return runtime

        effective_profile_dir = profile_dir or default_profile_root(profile_name)
        if ephemeral:
            effective_profile_dir = Path(tempfile.mkdtemp(prefix="wechat-reader-"))
        if strategy_value in {Strategy.AUTO, Strategy.LAUNCH}:
            try:
                launched_cdp_url = _launch_managed_browser_process(channel=channel, profile_dir=effective_profile_dir)
                runtime = _connect_attach_runtime(manager, playwright_error, cdp_url=launched_cdp_url)
                runtime.strategy = Strategy.LAUNCH
            except BridgeError:
                if strategy_value == Strategy.LAUNCH:
                    raise
            else:
                runtime.playwright_manager = manager
                return runtime

        if strategy_value in {Strategy.AUTO, Strategy.PLAYWRIGHT}:
            runtime = _launch_persistent_runtime(
                manager,
                playwright_error,
                channel="chromium",
                profile_dir=effective_profile_dir,
                headless=headless,
            )
            runtime.playwright_manager = manager
            runtime.strategy = Strategy.PLAYWRIGHT
            return runtime
    except Exception:  # noqa: BLE001
        manager.stop()
        raise

    manager.stop()
    raise BridgeError(f"Unsupported strategy: {strategy_value}")


def find_matching_page(runtime: BrowserRuntime, url: str) -> PageMatch:
    target_host = urlsplit(url).netloc.lower()
    for page in runtime.context.pages:
        if not getattr(page, "url", ""):
            continue
        if page.url == url:
            return PageMatch(page=page, reused_existing_tab=True)
    for page in runtime.context.pages:
        if not getattr(page, "url", ""):
            continue
        page_host = urlsplit(page.url).netloc.lower()
        if target_host and page_host == target_host and "mp.weixin.qq.com" in page_host:
            return PageMatch(page=page, reused_existing_tab=True)
    for page in runtime.context.pages:
        if not getattr(page, "url", "") or page.url in {"about:blank", "chrome://newtab/"}:
            return PageMatch(page=page, reused_existing_tab=False)
    return PageMatch(page=runtime.context.new_page(), reused_existing_tab=False)


def _navigate(page: Any, url: str, timeout_seconds: int, timeout_error: type[BaseException], playwright_error: type[BaseException]) -> None:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
    except timeout_error:
        return
    except playwright_error as exc:
        raise BridgeError(f"Navigation failed: {exc}") from exc


def _status_for_bridge_error(exc: BridgeError) -> PageStatus:
    message = str(exc).lower()
    if "playwright is not installed" in message:
        return PageStatus.BROWSER_NOT_READY
    if "no attachable browser found" in message or "no browser executable found" in message:
        return PageStatus.BROWSER_NOT_FOUND
    if (
        "failed to connect to existing browser via cdp" in message
        or "launched browser did not expose a cdp endpoint in time" in message
        or "failed to launch persistent browser context" in message
    ):
        return PageStatus.BROWSER_NOT_READY
    return PageStatus.NAVIGATION_FAILED


def _bridge_metadata(
    *,
    original_url: str,
    effective_url: str,
    runtime: BrowserRuntime | None = None,
    reused_existing_tab: bool | None = None,
    navigation_performed: bool | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "requested_url": original_url,
        "effective_url": effective_url,
        "url_unwrapped": original_url != effective_url,
    }
    if runtime is not None:
        metadata["runtime_strategy"] = runtime.strategy.value
        metadata["cdp_url"] = runtime.cdp_url
    if reused_existing_tab is not None:
        metadata["reused_existing_tab"] = reused_existing_tab
    if navigation_performed is not None:
        metadata["navigation_performed"] = navigation_performed
    return metadata


def open_article_sync(
    url: str,
    *,
    strategy: Strategy | str = Strategy.AUTO,
    cdp_url: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    channel: str = "chrome",
    profile_dir: Path | None = None,
    profile_name: str = "default",
    ephemeral: bool = False,
    wait_for_manual_verify: int = 0,
) -> ArticleResult:
    request_url = unwrap_wechat_article_url(url)
    try:
        runtime = open_runtime(
            strategy=strategy,
            cdp_url=cdp_url,
            channel=channel,
            profile_dir=profile_dir,
            profile_name=profile_name,
            ephemeral=ephemeral,
            headless=False,
        )
        _, timeout_error, playwright_error = load_playwright()
        match = find_matching_page(runtime, request_url)
        navigation_performed = match.page.url != request_url
        if navigation_performed:
            _navigate(match.page, request_url, timeout, timeout_error, playwright_error)
        result = wait_for_article_result(match.page, 1_500, playwright_error, target_id=match.target_id)
        result.metadata.update(
            _bridge_metadata(
                original_url=url,
                effective_url=request_url,
                runtime=runtime,
                reused_existing_tab=match.reused_existing_tab,
                navigation_performed=navigation_performed,
            )
        )
        if wait_for_manual_verify > 0 and result.status in {PageStatus.CAPTCHA_REQUIRED, PageStatus.RATE_LIMITED}:
            result = wait_for_manual_resolution(
                match.page,
                wait_for_manual_verify * 1000,
                playwright_error,
                target_id=match.target_id,
            )
            result.metadata.update(
                _bridge_metadata(
                    original_url=url,
                    effective_url=request_url,
                    runtime=runtime,
                    reused_existing_tab=match.reused_existing_tab,
                    navigation_performed=navigation_performed,
                )
            )
            return result
        return result
    except BridgeError as exc:
        return ArticleResult.status_only(
            _status_for_bridge_error(exc),
            url=url,
            hint=str(exc),
            metadata=_bridge_metadata(original_url=url, effective_url=request_url),
        )
    finally:
        if "runtime" in locals():
            runtime.close()


def read_article_sync(
    url: str,
    *,
    strategy: Strategy | str = Strategy.AUTO,
    cdp_url: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    channel: str = "chrome",
    profile_dir: Path | None = None,
    profile_name: str = "default",
    ephemeral: bool = False,
    wait_for_manual_verify: int = 0,
) -> ArticleResult:
    request_url = unwrap_wechat_article_url(url)
    try:
        runtime = open_runtime(
            strategy=strategy,
            cdp_url=cdp_url,
            channel=channel,
            profile_dir=profile_dir,
            profile_name=profile_name,
            ephemeral=ephemeral,
            headless=False,
        )
        _, timeout_error, playwright_error = load_playwright()
        match = find_matching_page(runtime, request_url)
        navigation_performed = match.page.url != request_url
        if navigation_performed:
            _navigate(match.page, request_url, timeout, timeout_error, playwright_error)
        result = wait_for_article_result(match.page, timeout * 1000, playwright_error, target_id=match.target_id)
        result.metadata.update(
            _bridge_metadata(
                original_url=url,
                effective_url=request_url,
                runtime=runtime,
                reused_existing_tab=match.reused_existing_tab,
                navigation_performed=navigation_performed,
            )
        )
        if wait_for_manual_verify > 0 and result.status in {PageStatus.CAPTCHA_REQUIRED, PageStatus.RATE_LIMITED}:
            result = wait_for_manual_resolution(
                match.page,
                wait_for_manual_verify * 1000,
                playwright_error,
                target_id=match.target_id,
            )
            result.metadata.update(
                _bridge_metadata(
                    original_url=url,
                    effective_url=request_url,
                    runtime=runtime,
                    reused_existing_tab=match.reused_existing_tab,
                    navigation_performed=navigation_performed,
                )
            )
            return result
        return result
    except BridgeError as exc:
        return ArticleResult.status_only(
            _status_for_bridge_error(exc),
            url=url,
            hint=str(exc),
            metadata=_bridge_metadata(original_url=url, effective_url=request_url),
        )
    finally:
        if "runtime" in locals():
            runtime.close()


async def open_article(url: str, **kwargs: Any) -> ArticleResult:
    return await asyncio.to_thread(open_article_sync, url, **kwargs)


async def read_article(url: str, **kwargs: Any) -> ArticleResult:
    return await asyncio.to_thread(read_article_sync, url, **kwargs)
