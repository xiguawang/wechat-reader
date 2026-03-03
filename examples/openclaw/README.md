# OpenClaw 集成示例

本示例展示如何将 `wechat-reader` 作为本地桥接工具接入 OpenClaw 风格的 Agent。

提供两个入口：

- `wechat-reader-openclaw`：稳定的可执行入口，用于实际 Agent 集成
- `examples/openclaw/openclaw_wechat_bridge.py`：源码级示例脚本，逻辑相同

## 目标

当 Agent 遇到 `mp.weixin.qq.com` 链接时，应该：

1. 不直接用 HTTP 抓取
2. 打开或复用一个可见的桥接浏览器
3. 如果页面可读，返回文章内容
4. 如果微信拦截了页面，返回结构化的下一步动作

## 推荐流程

### 1. 首次尝试：通过桥接浏览器直接读取

```bash
wechat-reader-openclaw \
  read \
  "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --wait-for-manual-verify 90
```

典型返回：

- `next_action=return_article`：Agent 可以直接摘要或引用文章正文
- `next_action=ask_user_to_verify`：Agent 应提示用户在桥接浏览器中完成验证，然后重试
- `next_action=ask_user_to_retry`：Agent 应告知用户微信限频，稍后再试
- `next_action=guide_browser_setup`：Agent 应引导用户执行 `wechat-reader setup`

### 2. 如果页面被拦截

告诉用户类似这样的话：

> 我在桥接浏览器里打开了这篇微信文章，但微信要求先完成验证。请在弹出的浏览器窗口中完成验证，然后让我重试。

### 3. 重试读取

```bash
wechat-reader-openclaw \
  read \
  "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --wait-for-manual-verify 90
```

## 为什么需要这个 Wrapper

`wechat-reader` 返回的是详细的页面状态，比如 `captcha_required`、`article_not_rendered`。

OpenClaw 通常需要更高层的决策模型：

- Agent 下一步该做什么
- Agent 应该对用户说什么
- 文章内容现在是否可用

这个 Wrapper 将 `wechat-reader` 的结果转换为：

- `status`
- `next_action`
- `user_message`
- 成功时附带 `article`

与通用 CLI 不同，这个 Wrapper 在参数解析之后始终以退出码 `0` 结束，即使页面被拦截或限频。这样 OpenClaw 不会把正常的微信页面状态当作命令失败。

## JSON 示例

页面被拦截：

```json
{
  "tool": "wechat-reader",
  "status": "captcha_required",
  "next_action": "ask_user_to_verify",
  "user_message": "请在浏览器中完成验证，然后重试。"
}
```

成功读取：

```json
{
  "tool": "wechat-reader",
  "status": "ok",
  "next_action": "return_article",
  "user_message": "已读取微信文章：示例标题",
  "article": {
    "url": "https://mp.weixin.qq.com/...",
    "title": "示例标题",
    "author": "示例作者",
    "content": "..."
  }
}
```

## OpenClaw 路由建议

伪代码流程：

```text
if url.host == "mp.weixin.qq.com":
    result = run wechat-reader-openclaw read <url> --strategy launch --wait-for-manual-verify 90
    if result.next_action == "return_article":
        用 article.content 回答用户
    elif result.next_action == "ask_user_to_verify":
        提示用户在桥接浏览器中完成验证
    elif result.next_action == "guide_browser_setup":
        展示环境配置引导
    else:
        展示 result.user_message
```

## JSON Stdin 模式

如果工具调度器更适合通过 stdin 传参：

```bash
printf '%s\n' '{"url":"https://mp.weixin.qq.com/s?...","strategy":"launch","wait_for_manual_verify":90}' \
  | wechat-reader-openclaw read --stdin-json
```

## Schema 和环境检查

打印 Wrapper schema：

```bash
wechat-reader-openclaw schema --pretty
```

运行环境诊断：

```bash
wechat-reader-openclaw setup --pretty
```

## 注意事项

- 默认使用 `launch` 策略，除非用户已经开放了 CDP 浏览器端口
- 保持浏览器可见。隐藏或全新的自动化会话更容易触发微信风控
- 把 `captcha_required` 当作正常的状态流转，而不是致命错误

## Agent 话术建议

按 `next_action` 推荐的用户面对话术：

- `return_article`：「已成功读取微信文章，可以为你摘要或回答相关问题。」
- `ask_user_to_verify`：「我在桥接浏览器里打开了这篇微信文章，但微信要求先验证。请在浏览器窗口中完成验证，然后让我重试。」
- `ask_user_to_retry`：「微信暂时限频了这个页面，稍等一会儿再让我重试。」
- `guide_browser_setup`：「本地桥接浏览器还没准备好。请运行 `wechat-reader setup`，或启动带 CDP 端口的 Chrome，然后重试。」
- `install_dependencies`：「本地桥接缺少运行时依赖。请安装 Playwright 后重试。」
