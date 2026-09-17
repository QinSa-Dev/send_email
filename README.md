# send_email

让 agent 调用并发送邮件：**本机渲染 Markdown** + 多附件，邮箱密钥通过 `.env`
或环境变量配置，不会提交到公网。

```
send_email/
├── README.md
├── SKILL.md                # opencode/Claude skill 发现入口（含 name/description）
├── skill.yaml              # 自定义 exec 入口（命令路径可用 SEND_EMAIL_DIR 覆盖）
├── send.sh                 # agent 调用入口（stdin 读 JSON）
├── send_mail.py            # SMTP 发送 + 配置加载（.env / 环境变量）
├── render_markdown.py      # 本机 Markdown -> 邮件 HTML 渲染器
├── setup_mail.sh           # 交互式邮箱配置
├── install.sh              # 依赖检查 / 初始化配置
├── config/
│   ├── mail.env.example    # 配置模板
│   └── .gitignore          # 忽略 mail.env 等密钥文件
└── .gitignore
```

## 快速开始

```bash
git clone <your-gitlab-repo-url> send_email   # 或下载 ZIP 解压
cd send_email

./install.sh       # 检查 python3/jq，初始化 config/mail.env
./setup_mail.sh    # 交互式填写发件人、收件人、SMTP、授权码，可发测试邮件
```

## 移植到任意目录

skill 内部脚本用 `$(dirname "$0")` 自定位，克隆到任何路径都能运行：

- **opencode / Claude**：把该目录放入 `skills.paths`（如 `/root/skills`），
  会自动识别根目录的 `SKILL.md`。
- **skill.yaml 调用方**：命令默认 `/root/skills/send_email/send.sh`，可用环境
  变量覆盖：

  ```bash
  export SEND_EMAIL_DIR=/your/path/to/send_email
  ```

  若运行环境不解析 `${VAR}`，请把 `skill.yaml` 里的 `command` 改成实际路径。
- 依赖：`python3`、`jq`；可选 `markdown`/`markdown2`、`pygments`（缺失不影响使用）。

## 配置：优先用 `.env`

配置优先级：**进程环境变量 > `config/mail.env` > `.env` > 旧版 `mail_config.toml`**。

`config/mail.env`（由 `setup_mail.sh` 生成，权限 600）：

```dotenv
MAIL_FROM="sender@example.com"
MAIL_TO="receiver@example.com"
SMTP_HOST="smtp.example.com"
SMTP_PORT=587
SMTP_TOKEN="邮箱授权码"
SMTP_SSL=true
```

也可以完全不建文件，直接导出环境变量：

```bash
export MAIL_FROM="sender@example.com"
export MAIL_TO="receiver@example.com"
export SMTP_HOST="smtp.example.com"
export SMTP_PORT=587
export SMTP_TOKEN="邮箱授权码"
export SMTP_SSL=true
```

密钥安全：`config/mail.env`、`.env`、`config/mail_config.toml` 均在
`.gitignore` 中，部署/上传前会自动被忽略，避免泄露到公网。

## Markdown 本地渲染

多数邮箱客户端不会渲染 Markdown，因此发送前在本机转换为 HTML：

- 邮件为 `multipart/alternative`，同时包含**纯文本（Markdown 源码，降级显示）**
  与 **渲染后的 HTML**。
- `.md/.markdown` 正文文件、以及 `body_text`/stdin 正文默认按 Markdown 渲染。
- 渲染器优先使用 `markdown` / `markdown2`（若已安装），否则回退到**内置解析器**
  （零依赖，支持标题、列表、表格、代码块、引用、链接、图片、加粗/斜体/删除线）。
- 若系统装有 `pygments`，代码块会自动语法高亮。
- 发送 `.html` 文件时直接作为 HTML 正文；其它后缀按纯文本发送。

单独渲染预览：

```bash
python3 render_markdown.py report.md -o report.html
python3 render_markdown.py report.md --no-style
```

导出整封 `.eml` 预览（不发送）：

```bash
python3 send_mail.py --subject "测试" --body-file report.md --preview /tmp/mail.eml
```

## 被 agent 调用

`skill.yaml` 的 `exec.command` 指向 `send.sh`，agent 传入：

```json
{
  "subject": "【任务完成】",
  "body_file": "~/report.md",
  "body_text": null,
  "attachments": ["~/report.pdf"]
}
```

## 命令行手动使用

```bash
./send.sh <<'JSON'
{
  "subject": "【测试】",
  "body_text": "# 标题\n\n支持 **Markdown** 与附件",
  "attachments": ["~/report.pdf", "/tmp/screenshot.png"]
}
JSON
```

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 提示缺少配置项 / 未找到配置 | 运行 `./setup_mail.sh` 或导出环境变量 |
| 登录失败 / 535 | 确认用的是**授权码**而非登录密码 |
| 连接超时 | 检查 `SMTP_HOST` / `SMTP_PORT`，以及网络是否放行 |
| Markdown 表格/代码块排版不理想 | 安装 `markdown`（`python3 -m pip install markdown`） |
| 缺少 jq | 运行 `./install.sh` 查看安装建议 |