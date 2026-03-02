# OpenClaw Integration Example

This example shows how to use `mp-article-bridge` as a local bridge for an OpenClaw-style agent.

Two entrypoints are included:

- `mp-article-bridge-openclaw`: the stable exec wrapper intended for real agent integration
- `examples/openclaw/openclaw_wechat_bridge.py`: a source-tree example script that mirrors the same behavior

## Goal

When the agent sees an `mp.weixin.qq.com` URL, it should:

1. avoid direct HTTP fetch
2. open or reuse a visible bridge browser
3. read the page if possible
4. return a structured agent action when WeChat blocks the page

## Recommended Flow

### 1. First attempt: read directly through the bridge

```bash
mp-article-bridge-openclaw \
  read \
  "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --wait-for-manual-verify 90
```

Typical responses:

- `next_action=return_article`: the agent can summarize or quote the article body
- `next_action=ask_user_to_verify`: the agent should tell the user to complete verification in the visible bridge browser, then retry
- `next_action=ask_user_to_retry`: the agent should tell the user WeChat rate-limited the page
- `next_action=guide_browser_setup`: the agent should guide the user through `mp-article-bridge setup`

### 2. If the page is blocked

Tell the user something like:

> I opened the WeChat article in the bridge browser, but WeChat requires verification first. Complete the verification in the visible browser window, then ask me to retry reading.

### 3. Retry the read

```bash
mp-article-bridge-openclaw \
  read \
  "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --wait-for-manual-verify 90
```

## Why This Wrapper Exists

`mp-article-bridge` returns detailed page states such as `captcha_required` and `article_not_rendered`.

OpenClaw usually wants a higher-level decision model:

- what should the agent do next
- what should the agent say to the user
- whether article content is available right now

This wrapper converts `mp-article-bridge` results into:

- `status`
- `next_action`
- `user_message`
- `article` on success

Unlike the general CLI, this wrapper always exits with code `0` after argument parsing, even for blocked or rate-limited pages. That keeps OpenClaw from treating normal WeChat states as hard command failures.

## Example JSON

Blocked page:

```json
{
  "tool": "mp-article-bridge",
  "status": "captcha_required",
  "next_action": "ask_user_to_verify",
  "user_message": "Please complete verification in the browser, then retry."
}
```

Successful read:

```json
{
  "tool": "mp-article-bridge",
  "status": "ok",
  "next_action": "return_article",
  "user_message": "Read WeChat article: Example Title",
  "article": {
    "url": "https://mp.weixin.qq.com/...",
    "title": "Example Title",
    "author": "Example Author",
    "content": "..."
  }
}
```

## OpenClaw Routing Suggestion

Pseudo-flow:

```text
if url.host == "mp.weixin.qq.com":
    result = run mp-article-bridge-openclaw read <url> --strategy launch --wait-for-manual-verify 90
    if result.next_action == "return_article":
        answer from article.content
    elif result.next_action == "ask_user_to_verify":
        ask the user to complete verification in the bridge browser
    elif result.next_action == "guide_browser_setup":
        show setup guidance
    else:
        present result.user_message
```

## JSON Stdin Mode

For tool runners that prefer stdin payloads over argv:

```bash
printf '%s\n' '{"url":"https://mp.weixin.qq.com/s?...","strategy":"launch","wait_for_manual_verify":90}' \
  | mp-article-bridge-openclaw read --stdin-json
```

## Schema And Setup

Print the wrapper schema:

```bash
mp-article-bridge-openclaw schema --pretty
```

Run setup diagnostics in wrapper form:

```bash
mp-article-bridge-openclaw setup --pretty
```

## Notes

- Use `launch` as the default OpenClaw strategy unless the user already exposes a CDP browser.
- Keep the browser visible. Hidden or fresh automation sessions are more likely to trigger WeChat checks.
- Treat `captcha_required` as a normal state transition, not a fatal tool error.

## Chat-Facing Prompt Suggestions

Suggested user-facing copy by `next_action`:

- `return_article`: "I read the WeChat article successfully. I can now summarize it or answer questions from the article body."
- `ask_user_to_verify`: "I opened the WeChat article in the bridge browser, but WeChat still requires verification. Complete verification in the visible browser window, then ask me to retry."
- `ask_user_to_retry`: "WeChat is temporarily rate-limiting this page. Wait a bit and ask me to retry."
- `guide_browser_setup`: "The local browser bridge is not ready yet. Run `mp-article-bridge setup`, or start Chrome with a reachable CDP port, then retry."
- `install_dependencies`: "The local bridge is missing runtime dependencies. Install Playwright and retry the command."
