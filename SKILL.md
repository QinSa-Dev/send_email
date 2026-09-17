---
name: send_email
description: Send email notifications with local Markdown rendering and multiple file attachments. Use when asked to email a report, send task results, push alerts with attachments, or send files to a mailbox (发送邮件、邮件通知、带附件发送报告). Reads recipient/credentials from a local .env or environment variables, so secrets are never committed.
license: MIT
compatibility: Requires python3 and jq on PATH. Optional markdown/markdown2 and pygments improve rendering. Network access to your SMTP server is required.
metadata:
  author: opencode
  version: "2.0.0"
---

# send_email

Send email with **local Markdown rendering** and **file attachments**. Credentials
come from `config/mail.env` (git-ignored) or environment variables.

## Path resolution

This skill can be cloned to any directory, so resolve its location first. Set
`SKILL_DIR` to the directory containing this SKILL.md, then run commands as
written:

```bash
export SKILL_DIR=<absolute path of the directory containing this SKILL.md>
```

## Setup (once)

```bash
"$SKILL_DIR/install.sh"      # check python3/jq, create config/mail.env
"$SKILL_DIR/setup_mail.sh"   # interactive: SMTP host, port, account, token
```

Configuration priority: process environment variables > `SEND_EMAIL_CONFIG` >
`config/mail.env` > `.env` > legacy `config/mail_config.toml`. Fields:
`MAIL_FROM`, `MAIL_TO`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_TOKEN`, `SMTP_SSL`.
Never commit `config/mail.env`; it is already covered by `.gitignore`.

## Sending (how the agent calls it)

Pipe a JSON object to `send.sh` on stdin:

```bash
"$SKILL_DIR/send.sh" <<'JSON'
{
  "subject": "【task done】",
  "body_file": "~/report.md",
  "body_text": null,
  "attachments": ["~/report.pdf"]
}
JSON
```

Fields:

| field | required | meaning |
| --- | --- | --- |
| `subject` | yes | Email subject |
| `body_file` | no | Path to a body file; `.md` is rendered locally to HTML |
| `body_text` | no | Inline body text, rendered as Markdown; may be empty |
| `attachments` | no | Array of attachment paths, supports `~` |

`body_text` (non-empty) takes precedence, else `body_file`, else send an empty body.

## Markdown rendering

Most mail clients do not render Markdown, so bodies are converted to HTML **on
the local machine** before sending. The email is `multipart/alternative` with
both the plain-text Markdown source (fallback) and the rendered HTML.

- `.md`/`.markdown` files, `body_text`, and stdin are rendered as Markdown.
- `.html` files are used as the HTML part directly; other extensions send as plain text.
- Prefers `markdown`/`markdown2`; falls back to a built-in zero-dependency
  renderer (headings, lists, tables, code blocks, quotes, links, images).
- `pygments`, if present, adds syntax highlighting.

Preview without sending:

```bash
python3 "$SKILL_DIR/render_markdown.py" report.md -o report.html
python3 "$SKILL_DIR/send_mail.py" --subject "test" --body-file report.md --preview /tmp/mail.eml
```

## Examples

```bash
# Markdown file as body + two attachments
"$SKILL_DIR/send.sh" <<'JSON'
{"subject":"Weekly report","body_file":"~/weekly.md","attachments":["~/weekly.pdf","~/chart.png"]}
JSON

# Inline Markdown body
"$SKILL_DIR/send.sh" <<'JSON'
{"subject":"Alert","body_text":"# CPU high\n\n- node: web-01\n- value: 95%","attachments":[]}
JSON

# Empty body
"$SKILL_DIR/send.sh" <<'JSON'
{"subject":"Ping","body_text":"","attachments":[]}
JSON
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Missing config items | Run `setup_mail.sh` or export the SMTP variables |
| Login failed / 535 | Use the SMTP **authorization code**, not the account password |
| Connection timeout | Check `SMTP_HOST`/`SMTP_PORT` and network egress |
| `jq` not found | Run `install.sh` for install hints |
| Poor table/code rendering | `python3 -m pip install markdown` |