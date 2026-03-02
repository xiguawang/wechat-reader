# wechat-reader

Local browser bridge for agents to read WeChat Official Account articles from an authenticated browser session.

## What This Is

`wechat-reader` is not a generic "bypass WeChat anti-bot" scraper.

It is a local bridge that helps AI agents and automation tools:

- connect to an existing browser session or a managed bridge browser
- open a WeChat article URL when needed
- detect whether the page is readable, blocked, rate-limited, or still rendering
- extract article content from the live DOM when the page is actually readable

This project is designed for agent workflows such as OpenClaw, MCP-based tools, Claude Code, Codex, or custom local assistants.

## Why This Exists

WeChat article pages are hostile to direct automation:

- plain HTTP fetches usually fail or redirect to verification pages
- fresh Playwright/browser automation sessions often trigger `wappoc_appmsgcaptcha`
- even visible browsers may hit "environment abnormal" or "operation too frequent"

So the practical goal is not "fetch any article headlessly".

The practical goal is:

- reuse a browser session the user can actually verify
- return structured status instead of vague failure
- let an agent guide the user when manual verification is required

## Current Project Status

This repository is in early prototype stage.

Currently implemented and locally validated:

- CLI commands: `setup`, `tabs`, `open`, `read`
- browser strategies: `auto`, `attach`, `launch`, `playwright`
- managed bridge profile under `~/.wechat-reader/profiles/default`
- structured page status detection for WeChat pages
- manual verification wait mode for blocked pages

Real-world validation so far:

- the bridge browser can be launched or reused
- real WeChat links can be opened and classified
- blocked pages correctly return `captcha_required`
- the prototype has not yet reliably completed a full real-world article read on a link that remains behind WeChat verification

That limitation is intentional in the docs. The current value is reliable state detection plus browser/session reuse, not a false promise of universal extraction.

## Core Ideas

### 1. Prefer attach over fresh automation

If the user already has a browser session with a valid WeChat state, reuse it.

### 2. Use a persistent bridge profile

If no attachable browser is available, `launch` starts a managed browser with a persistent profile, so verification state can survive across runs.

Default bridge profile:

- macOS / Linux: `~/.wechat-reader/profiles/default`
- Windows: `%USERPROFILE%\.wechat-reader\profiles\default`

### 3. Return structured status

Instead of pretending every page is readable, return explicit status:

- `ok`
- `captcha_required`
- `rate_limited`
- `article_not_rendered`
- `unsupported_page`
- `browser_not_ready`
- `browser_not_found`
- `navigation_failed`

## Installation

Python 3.12+ is required.

### pipx

```bash
pipx install .
python -m playwright install chromium
```

### pip

```bash
pip install -e .
python -m playwright install chromium
```

Chrome is recommended for real-world use. Chromium / Playwright fallback is kept as an explicit compatibility path, not the primary strategy.

## Quick Start

### 1. Diagnose the environment

```bash
python -m wechat_reader setup
```

Typical output shows:

- whether Chrome is installed
- whether any CDP endpoint is reachable
- the default bridge profile path
- the recommended launch command

### 2. Launch a managed browser bridge

```bash
python -m wechat_reader open "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --channel chrome \
  --json
```

This will:

- launch or reuse a managed bridge browser
- navigate to the WeChat URL
- return current page status

### 3. Wait for manual verification and retry reading

```bash
python -m wechat_reader read "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --channel chrome \
  --wait-for-manual-verify 90 \
  --json
```

If WeChat blocks the page, the command will wait on the same page for up to 90 seconds so the user can complete verification in the browser.

If the input URL is a WeChat verification wrapper such as `mp/wappoc_appmsgcaptcha?...&target_url=...`, `wechat-reader` will unwrap it to the real article URL before matching tabs or navigating. This avoids sending an already-verified browser tab back to the captcha entry page.

### 4. Attach to an existing browser

```bash
python -m wechat_reader read "https://mp.weixin.qq.com/s?..." \
  --strategy attach \
  --cdp-url http://127.0.0.1:9222 \
  --json
```

### 5. List current WeChat tabs

```bash
python -m wechat_reader tabs --wechat-only --json
```

## CLI

### `setup`

Diagnose prerequisites and print recommended launch guidance.

```bash
python -m wechat_reader setup
python -m wechat_reader setup --json
```

### `tabs`

List attachable tabs from a browser exposing CDP.

```bash
python -m wechat_reader tabs --wechat-only
python -m wechat_reader tabs --wechat-only --json
```

### `open`

Open a URL in a managed or attached browser and report page status without requiring full article extraction.

```bash
python -m wechat_reader open "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --channel chrome \
  --json
```

### `read`

High-level command: reuse an existing matching tab if possible, otherwise navigate according to strategy, then attempt extraction.

```bash
python -m wechat_reader read "https://mp.weixin.qq.com/s?..." \
  --strategy auto \
  --timeout 30 \
  --json
```

Save markdown on success:

```bash
python -m wechat_reader read "https://mp.weixin.qq.com/s?..." \
  --output ./articles
```

This also works with previously shared captcha wrapper links after verification is complete. The wrapper URL is normalized to its `target_url` before reading and saving.

## Strategy Model

### `auto`

Recommended default:

1. try attach
2. fall back to managed launch
3. fall back to Playwright persistent mode

### `attach`

Only connect to an existing browser CDP endpoint. If none is available, fail with a structured `browser_not_found` status.

If the requested URL is a captcha wrapper link and the corresponding real article tab already exists, attach mode will reuse the real article tab instead of navigating back to the wrapper URL.

### `launch`

Launch or reuse a managed Chrome/Chromium bridge browser using a persistent profile controlled by `wechat-reader`.

This is the recommended fallback when the user does not already run Chrome with a debug port.

### `playwright`

Explicit compatibility fallback. Useful for development or non-Chrome environments, but more likely to trigger WeChat anti-bot checks.

## Key Options

- `--timeout <seconds>`: article read timeout, default `30`
- `--wait-for-manual-verify <seconds>`: wait on blocked pages for user verification
- `--cdp-url <url>`: connect to an existing debug browser
- `--channel chrome|chromium`: choose browser family for launch
- `--profile-dir <path>`: explicit bridge profile directory
- `--profile-name <name>`: named profile under `~/.wechat-reader/profiles/`
- `--ephemeral`: use a temporary profile for debugging only

## OpenClaw Example

An OpenClaw-oriented wrapper is included under [examples/openclaw/README.md](./examples/openclaw/README.md).

Use it when you want the tool to return agent-friendly fields such as:

- `next_action`
- `user_message`
- `article` on success

Example:

```bash
wechat-reader-openclaw \
  read \
  "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --wait-for-manual-verify 90
```

The OpenClaw wrapper is implemented in [wechat_reader/openclaw_tool.py](./wechat_reader/openclaw_tool.py) and is intended to be the stable executable interface for agent runtimes.

## Output Model

Successful result:

```json
{
  "status": "ok",
  "url": "https://mp.weixin.qq.com/...",
  "title": "Article title",
  "author": "Author",
  "content": "Article body",
  "fetched_at": "2026-03-02T00:00:00Z",
  "metadata": {
    "requested_url": "https://mp.weixin.qq.com/mp/wappoc_appmsgcaptcha?...",
    "effective_url": "https://mp.weixin.qq.com/s?...",
    "url_unwrapped": true,
    "runtime_strategy": "attach",
    "cdp_url": "http://127.0.0.1:9222",
    "reused_existing_tab": true,
    "navigation_performed": false
  }
}
```

Blocked result:

```json
{
  "status": "captcha_required",
  "url": "https://mp.weixin.qq.com/...",
  "hint": "Please complete verification in the browser, then retry."
}
```

### Metadata Notes

- `requested_url`: the raw input URL the caller passed in
- `effective_url`: the URL actually used for tab matching and navigation after wrapper unwrapping
- `url_unwrapped`: whether a captcha wrapper URL was normalized to `target_url`
- `runtime_strategy`: the strategy that actually ran, such as `attach` or `launch`
- `reused_existing_tab`: whether an existing browser tab was reused
- `navigation_performed`: whether `wechat-reader` had to navigate the page during this call

These fields are useful when a link appears to "bounce" between a captcha page and the article page, or when you need to confirm whether attach mode reused the already-verified tab.

## Python API

Public exports:

```python
from wechat_reader import (
    list_wechat_tabs,
    list_wechat_tabs_sync,
    open_article,
    open_article_sync,
    read_article,
    read_article_sync,
)
```

Example:

```python
from wechat_reader import read_article_sync

result = read_article_sync(
    "https://mp.weixin.qq.com/s?...",
    strategy="launch",
    timeout=30,
    wait_for_manual_verify=90,
)

print(result.status, result.hint)
```

## OpenClaw / Agent Usage

The intended agent flow is:

1. agent receives a WeChat article URL
2. agent calls `wechat-reader open` or `wechat-reader read`
3. if status is `ok`, agent consumes content
4. if status is `captcha_required` or `rate_limited`, agent tells the user to complete verification in the managed browser and retry

This project is meant to be a local browser-side primitive for agents, not a hidden cloud scraping backend.

Real-world validation on March 2, 2026:

- attach mode against a live WeChat verification page returned `captcha_required`
- the OpenClaw wrapper mapped that result to `next_action = ask_user_to_verify`
- this is the intended behavior for `wappoc_appmsgcaptcha` pages

## Mobile-Initiated Workflows

Pure mobile-side DOM access is usually not realistic because WeChat links often open inside mobile WebViews that do not expose stable debugging interfaces.

The recommended mobile-friendly architecture is:

- user sends the link from mobile
- agent forwards the task to a desktop `wechat-reader` bridge
- desktop browser handles verification and reading
- agent returns the result to the mobile conversation

## Known Limitations

- WeChat anti-bot behavior can change without warning
- some links may still require repeated manual verification
- "operation too frequent" is a real runtime condition, not something this tool can guarantee away
- a visible browser plus persistent profile improves usability, but does not guarantee article access
- local CDP discovery can behave differently under restricted environments or sandboxes
- CDP attach may fail with local `EPERM` errors inside a sandbox even when the same Chrome session works outside the sandbox
- when validating agent integrations, prefer running the actual attach/read command outside restrictive sandboxes before treating CDP failures as product bugs

## Development

Run tests:

```bash
python -m unittest discover -s tests -v
```

Basic CLI check:

```bash
python -m wechat_reader setup
python -m wechat_reader read --help
```

## Roadmap

- improve managed bridge discovery and reuse
- add clearer OpenClaw integration examples
- expose MCP server support
- improve recovery flow after manual verification succeeds
- add better troubleshooting docs and platform-specific setup guidance

## License

MIT
