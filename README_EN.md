# wechat-reader

CLI + MCP server + Python API for reading WeChat Official Account articles from a verified browser session.

> [中文版](./README.md)

`wechat-reader` is a WeChat article reader for AI agents and local automation. It reuses a real browser session when possible, returns structured page states such as `ok` and `captcha_required`, and exposes the same local bridge through CLI, MCP, and Python.

## Who Is This For

If your AI agent or automation pipeline needs to **reliably** read WeChat Official Account (公众号) articles, this tool is for you.

**The problem:** WeChat article URLs are notoriously unfriendly to programmatic access. Standard HTTP fetching (`curl`, `requests`, `web_fetch`) often returns blank pages, CAPTCHAs, or login walls — and fails silently, so your agent doesn't even know it got nothing useful.

**What this tool does differently:**
- Uses a real browser session to read articles the way a human would
- Returns structured statuses (`ok`, `captcha_required`, `rate_limited`) so your agent knows exactly what happened
- When verification is needed, tells the agent to ask the user — instead of silently returning garbage

**Typical use cases:**
- AI agent workflows that process WeChat article links (summarization, translation, knowledge base ingestion)
- Content monitoring or competitive analysis pipelines
- Any automation where a WeChat link appears and needs to be read reliably

**Not for you if:** you only read an occasional WeChat article — just copy-paste the text. This tool is for when WeChat links show up in your automated pipeline and need to work every time.

## Interfaces

Use it through:

- `wechat-reader`: open, read, inspect, and export article content from a visible browser
- `wechat-reader-mcp`: expose the bridge as an MCP server for Claude, Codex, and other agent runtimes
- `wechat_reader`: import the Python API directly inside your own tooling

## Quick Start

Python 3.11+ is required.

### Install

```bash
git clone https://github.com/xiguawang/wechat-reader.git
cd wechat-reader
uv sync
uv run playwright install chromium
```

If you do not use `uv`, the fallback is:

```bash
pip install -e .
python -m playwright install chromium
```

### Read an article through the CLI

```bash
wechat-reader read "https://mp.weixin.qq.com/s?..." --json
```

### Diagnose the local browser environment

```bash
wechat-reader setup
```

### Start the MCP server

```bash
wechat-reader-mcp
```

### Use the Python API

```python
from wechat_reader import read_article_sync

result = read_article_sync("https://mp.weixin.qq.com/s?...", strategy="auto", timeout=30)
print(result.status, result.title)
```

## What You Get

- browser reuse via `attach`, `launch`, `playwright`, and `auto`
- structured statuses such as `ok`, `captcha_required`, `rate_limited`, and `browser_not_ready`
- markdown and JSON output from the CLI
- an MCP server with tools and resources
- a Python API for direct integration

## Screenshots

Representative terminal snapshots from local validation:

### Successful Read After Verification

![Successful read screenshot](docs/screenshots/read-ok.svg)

This shows the post-verification `status = ok` path, including wrapper URL unwrapping and tab reuse.

### Blocked Page Requiring Manual Verification

![Captcha required screenshot](docs/screenshots/captcha-required.svg)

This shows the OpenClaw-oriented blocked path with `captcha_required` and `next_action = ask_user_to_verify`.

### Real MCP Host Validation

![MCP validation screenshot](docs/screenshots/mcp-host-validation.svg)

This shows the real Codex-host MCP validation path used to confirm `wechat_setup` can be reached through a configured stdio MCP server.

## Current Status

This repository is a working local bridge with the core browser, CLI, Python API, OpenClaw, and MCP paths implemented.

Currently implemented and locally validated:

- CLI commands: `setup`, `tabs`, `open`, `read`
- browser strategies: `auto`, `attach`, `launch`, `playwright`
- managed bridge profile under `~/.wechat-reader/profiles/default`
- structured page status detection for WeChat pages
- manual verification wait mode for blocked pages
- stdio MCP server with tool-based access for agent runtimes
- fresh virtualenv install validation

Real-world validation so far:

- the bridge browser can be launched or reused
- real WeChat links can be opened and classified
- blocked pages correctly return `captcha_required`
- after manual verification, a real `wappoc_appmsgcaptcha` wrapper link was unwrapped to its article `target_url`
- the real article body was successfully read through attach mode from the verified Chrome tab
- the same validated read path also successfully saved markdown output
- a real Codex-host MCP run successfully called `wechat_setup`

## MCP Server

A stdio MCP server is included:

```bash
wechat-reader-mcp
```

Currently exposed tools:

- `wechat_read_article`
- `wechat_open_article`
- `wechat_list_tabs`
- `wechat_read_current_tab`
- `wechat_get_status`
- `wechat_setup`

Currently exposed resources:

- `wechat-reader://setup`
- `wechat-reader://tabs`
- project `README.md`
- OpenClaw integration `README.md`

The server implements `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, and `ping`, then delegates to the same local bridge logic used by the CLI and Python API.

### Example MCP Client Config

For MCP clients that launch stdio servers from JSON config:

```json
{
  "mcpServers": {
    "wechat-reader": {
      "command": "wechat-reader-mcp",
      "args": []
    }
  }
}
```

If you are running directly from the source tree instead of an installed package:

```json
{
  "mcpServers": {
    "wechat-reader": {
      "command": "python3",
      "args": ["-m", "wechat_reader.mcp_server"],
      "cwd": "/path/to/wechat-reader"
    }
  }
}
```

Recommended first checks after connecting:

1. call `wechat_setup`
2. call `wechat_list_tabs`
3. call `wechat_read_article` with a known WeChat article URL or wrapper URL

## CLI

### `setup`

Diagnose prerequisites and print recommended launch guidance.

```bash
wechat-reader setup
wechat-reader setup --json
```

### `tabs`

List attachable tabs from a browser exposing CDP.

```bash
wechat-reader tabs --wechat-only
wechat-reader tabs --wechat-only --json
```

### `open`

Open a URL in a managed or attached browser and report page status without requiring full article extraction.

```bash
wechat-reader open "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --channel chrome \
  --json
```

### `read`

High-level command: reuse an existing matching tab if possible, otherwise navigate according to strategy, then attempt extraction.

```bash
wechat-reader read "https://mp.weixin.qq.com/s?..." \
  --strategy auto \
  --timeout 30 \
  --json
```

Save markdown on success:

```bash
wechat-reader read "https://mp.weixin.qq.com/s?..." \
  --output ./articles
```

If the input URL is a WeChat verification wrapper such as `mp/wappoc_appmsgcaptcha?...&target_url=...`, `wechat-reader` will unwrap it to the real article URL before matching tabs or navigating. This avoids sending an already-verified browser tab back to the captcha entry page.

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

## Mobile-Initiated Workflows

Pure mobile-side DOM access is usually not realistic because WeChat links often open inside mobile WebViews that do not expose stable debugging interfaces.

The recommended mobile-friendly architecture is:

- user sends the link from mobile
- agent forwards the task to a desktop `wechat-reader` bridge
- desktop browser handles verification and reading
- agent returns the result to the mobile conversation

## Known Limitations

`wechat-reader` is not a generic "bypass WeChat anti-bot" scraper.

- WeChat anti-bot behavior can change without warning
- some links may still require repeated manual verification
- "operation too frequent" is a real runtime condition, not something this tool can guarantee away
- a visible browser plus persistent profile improves usability, but does not guarantee article access
- local CDP discovery can behave differently under restricted environments or sandboxes
- CDP attach may fail with local `EPERM` errors inside a sandbox even when the same Chrome session works outside the sandbox
- when validating agent integrations, prefer running the actual attach/read command outside restrictive sandboxes before treating CDP failures as product bugs

## Public Release Readiness

Before making the repository public, the minimum release bar should be:

- clear English and Chinese README coverage
- a committed open-source license file
- passing CI plus passing local tests
- explicit documentation of limitations and verification-dependent flows
- at least one real-world validated read path from verification to extraction

Current state:

- English README: present
- Chinese README: present
- LICENSE file: present
- GitHub Actions CI: present
- local unit tests and compile check: passing
- real local verification and markdown export: completed
- real MCP host validation: completed
- fresh virtualenv install validation: completed

Still recommended before broad promotion:

- decide whether the repository should stay private a little longer or move to public visibility

## Development

Run tests:

```bash
python -m unittest discover -s tests -v
```

Basic CLI check:

```bash
wechat-reader setup
wechat-reader read --help
```

## Roadmap

- improve managed bridge discovery and reuse
- add clearer OpenClaw integration examples
- add screenshots and public-facing walkthroughs
- improve recovery flow after manual verification succeeds
- add better troubleshooting docs and platform-specific setup guidance

## License

MIT
