# mp-article-bridge

面向 AI Agent 的本地浏览器桥接工具，用于在用户已登录、已验证的浏览器会话中读取微信公众号文章。

## 这是什么

`mp-article-bridge` 不是一个承诺“稳定绕过微信风控”的通用抓取器。

它的目标更克制，也更真实：

- 连接用户现有浏览器，或启动一个受控的 bridge 浏览器
- 在需要时主动打开公众号文章链接
- 判断页面当前是可读、需验证、限流，还是尚未渲染完成
- 当页面真实可读时，从当前 DOM 提取标题、作者和正文

这个项目面向本地 Agent 工作流，例如 OpenClaw、MCP 客户端、Claude Code、Codex 或自定义桌面助手。

## 当前状态

当前仓库已经具备一条可工作的主链路：

- CLI：`setup`、`tabs`、`open`、`read`
- 浏览器策略：`auto`、`attach`、`launch`、`playwright`
- Python API
- OpenClaw wrapper
- stdio MCP server
- GitHub Actions CI

已经完成的本地真实验证包括：

- 识别真实微信验证页并返回 `captcha_required`
- 用户手动完成验证后，复用已验证的 Chrome tab 读取正文
- 自动将 `wappoc_appmsgcaptcha?...target_url=...` 解包为真实文章 URL
- 成功保存 markdown 输出

## 核心思路

### 优先复用已有浏览器

如果用户当前浏览器里已经有通过验证的微信页面，应优先 attach，而不是新建一个更容易触发风控的自动化会话。

### 使用持久化 bridge profile

当没有可 attach 的浏览器时，`launch` 会启动一个带持久化 profile 的 bridge 浏览器，让首次人工验证可以沉淀到后续运行中。

默认 profile 路径：

- macOS / Linux: `~/.wechat-reader/profiles/default`
- Windows: `%USERPROFILE%\.wechat-reader\profiles\default`

### 返回结构化状态

工具不会把所有失败都伪装成“超时”。

常见状态包括：

- `ok`
- `captcha_required`
- `rate_limited`
- `article_not_rendered`
- `unsupported_page`
- `browser_not_ready`
- `browser_not_found`
- `navigation_failed`

## 安装

要求 Python 3.12+。

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

真实使用时更推荐 Chrome。Chromium / Playwright fallback 主要用于兼容和开发，不是首选路径。

## 快速开始

### 1. 检查环境

```bash
mp-article-bridge setup
```

### 2. 启动 bridge 浏览器

```bash
mp-article-bridge open "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --channel chrome \
  --json
```

### 3. 等待用户手动验证后继续读取

```bash
mp-article-bridge read "https://mp.weixin.qq.com/s?..." \
  --strategy launch \
  --channel chrome \
  --wait-for-manual-verify 90 \
  --json
```

如果输入的是微信验证包装链接，例如 `mp/wappoc_appmsgcaptcha?...&target_url=...`，工具会先解包到真实文章 URL，再做 tab 匹配和导航，避免把已验证页面重新带回验证码入口。

### 4. 连接已有浏览器

```bash
mp-article-bridge read "https://mp.weixin.qq.com/s?..." \
  --strategy attach \
  --cdp-url http://127.0.0.1:9222 \
  --json
```

### 5. 列出当前微信标签页

```bash
mp-article-bridge tabs --wechat-only --json
```

## MCP Server

项目内置了一个最小可用的 stdio MCP server：

```bash
mp-article-bridge-mcp
```

当前暴露的 tools：

- `wechat_read_article`
- `wechat_open_article`
- `wechat_list_tabs`
- `wechat_read_current_tab`
- `wechat_get_status`
- `wechat_setup`

当前暴露的 resources：

- `mp-article-bridge://setup`
- `mp-article-bridge://tabs`
- 项目 `README.md`
- OpenClaw 集成 `README.md`

## 限制说明

- 微信风控可能随时变化
- 某些链接仍然需要用户先手动完成验证
- “操作频繁”是真实运行状态，不是这个工具能彻底消除的问题
- 受限沙箱环境下，CDP attach 可能出现本地 `EPERM`
- 移动端更适合“移动端发起，桌面端 bridge 执行”的模式

## 对外公开前的状态

当前已经达到“可公开仓库并让技术用户试用”的程度，但还不算大范围宣传级别的成熟产品。

已经具备：

- 核心功能可用
- 本地真实验证跑通
- 单元测试通过
- CI 已配置
- MCP 基础接入已完成

仍建议继续补的内容：

- README 截图
- 干净环境安装验证
- 真实 MCP 客户端端到端验证

## 许可证

MIT
