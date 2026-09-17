#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""send_mail.py — 通过 SMTP 发送邮件，支持本地渲染 Markdown 与多附件。

仅依赖 Python 标准库（若已安装 markdown/pygments 会获得更好的渲染效果）。
配置从 .env 文件读取，也可直接使用进程环境变量。字段：

    MAIL_FROM / SMTP_HOST / SMTP_PORT / SMTP_TOKEN / SMTP_SSL
    MAIL_TO（默认收件人，多个用逗号分隔）

配置文件查找顺序：--config 指定 > 进程环境变量 > config/mail.env >
config/mail_config.toml（旧格式，兼容）。真实配置已被 .gitignore 忽略，
请勿提交到公网仓库。

命令行示例：
    python3 send_mail.py --subject "标题" --body-file report.md \
        --attachment a.pdf --attachment ~/b.png
    echo "# 正文" | python3 send_mail.py --subject "标题" --body-stdin
    python3 send_mail.py --subject "标题" --body-file r.md --preview /tmp/mail.eml
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

import render_markdown

HERE = Path(__file__).resolve().parent
ENV_CANDIDATES = [HERE / "config" / "mail.env", HERE / ".env"]
LEGACY_TOML = HERE / "config" / "mail_config.toml"

# 兼容不同写法的环境变量名（取第一个存在的）
ENV_ALIASES = {
    "from_addr": ("MAIL_FROM", "SMTP_FROM", "FROM_ADDR"),
    "to_addr": ("MAIL_TO", "SMTP_TO", "TO_ADDR"),
    "smtp_host": ("SMTP_HOST", "MAIL_SMTP_HOST"),
    "smtp_port": ("SMTP_PORT", "MAIL_SMTP_PORT"),
    "token": ("SMTP_TOKEN", "MAIL_TOKEN", "SMTP_PASSWORD", "MAIL_PASSWORD"),
    "smtp_ssl": ("SMTP_SSL", "MAIL_SMTP_SSL"),
}
REQUIRED = ("from_addr", "to_addr", "smtp_host", "token")
MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd")
HTML_SUFFIXES = (".html", ".htm")


# --------------------------------------------------------------------------- #
# 配置加载
# --------------------------------------------------------------------------- #
def parse_env_file(path: Path) -> dict:
    """解析 KEY=VALUE 形式的 .env 文件。"""
    cfg: dict = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            val = val[1:-1]
        cfg[key.strip()] = val
    return cfg


def parse_toml_file(path: Path) -> dict:
    """解析旧版扁平 TOML（key = value）。"""
    cfg: dict = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            val = val[1:-1]
        cfg[key.strip()] = val
    return cfg


def load_config(explicit: str | None) -> tuple:
    """返回 (配置字典, 来源说明)。"""
    raw: dict = {}
    source = "进程环境变量"
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            sys.exit("❌ 指定的配置文件不存在：%s" % path)
        raw = parse_toml_file(path) if path.suffix == ".toml" else parse_env_file(path)
        source = str(path)
    else:
        for cand in ENV_CANDIDATES:
            if cand.is_file():
                raw = parse_env_file(cand)
                source = str(cand)
                break
        else:
            if LEGACY_TOML.is_file():
                raw = parse_toml_file(LEGACY_TOML)
                source = str(LEGACY_TOML)

    cfg: dict = {}
    for field, names in ENV_ALIASES.items():
        for name in names:
            if os.environ.get(name):
                cfg[field] = os.environ[name]
                break
        if field not in cfg and raw.get(field):
            cfg[field] = raw[field]
        if field not in cfg:
            for name in names:
                if raw.get(name):
                    cfg[field] = raw[name]
                    break
    return cfg, source


def as_bool(val, default: bool = False) -> bool:
    if val is None or val == "":
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on", "y")


def expand_path(path: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(path))).resolve()


# --------------------------------------------------------------------------- #
# 邮件构建与发送
# --------------------------------------------------------------------------- #
def split_recipients(raw: str) -> list:
    return [x for x in re.split(r"[,;\s]+", raw or "") if x]


def build_message(cfg, subject, body_text, attachments, body_kind) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = ", ".join(split_recipients(cfg.get("to_addr", "")))
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    text = body_text
    msg.set_content(text if text else " ")
    if text:
        if body_kind == "markdown":
            msg.add_alternative(render_markdown.render_markdown_to_html(text), subtype="html")
        elif body_kind == "html":
            msg.add_alternative(text, subtype="html")

    for item in attachments:
        path = expand_path(item)
        if not path.is_file():
            raise FileNotFoundError("附件不存在：%s" % path)
        ctype, encoding = mimetypes.guess_type(str(path))
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(
            path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name
        )
    return msg


def send_message(cfg, msg) -> None:
    host = cfg["smtp_host"]
    use_ssl = as_bool(cfg.get("smtp_ssl"), default=False)
    port = int(cfg.get("smtp_port") or 0) or (465 if use_ssl else 587)
    server = (
        smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30)
        if (use_ssl and port == 465)
        else smtplib.SMTP(host, port, timeout=30)
    )
    with server:
        if not (use_ssl and port == 465):
            server.ehlo()
            if use_ssl:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
        server.login(cfg["from_addr"], cfg.get("token", ""))
        server.send_message(msg)


def read_body(args) -> tuple:
    """返回 (正文文本, 类型)：markdown / html / plain。"""
    if args.body_stdin:
        return sys.stdin.read(), "markdown"
    if args.body_text is not None:
        return args.body_text, ("plain" if args.plain else "markdown")
    if args.body_file:
        path = expand_path(args.body_file)
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
        if args.markdown:
            kind = "markdown"
        elif args.plain:
            kind = "plain"
        elif suffix in MARKDOWN_SUFFIXES:
            kind = "markdown"
        elif suffix in HTML_SUFFIXES:
            kind = "html"
        else:
            kind = "plain"
        return text, kind
    return "", "plain"


def main() -> int:
    parser = argparse.ArgumentParser(description="通过 SMTP 发送邮件（支持 Markdown 与附件）")
    parser.add_argument("--config", help="配置文件路径（.env 或旧版 .toml）")
    parser.add_argument("--subject", required=True, help="邮件标题")
    parser.add_argument("--body-file", help="正文文件路径；.md 会自动本地渲染")
    parser.add_argument("--body-text", help="直接提供的正文文本")
    parser.add_argument("--body-stdin", action="store_true", help="从标准输入读取正文")
    parser.add_argument("--markdown", action="store_true", help="强制按 Markdown 渲染正文")
    parser.add_argument("--plain", action="store_true", help="强制按纯文本发送正文")
    parser.add_argument("--attachment", action="append", default=[], help="附件路径，可重复")
    parser.add_argument("--preview", metavar="EML", help="不发送，仅把邮件内容写入 .eml 预览文件")
    args = parser.parse_args()

    cfg, source = load_config(args.config)
    missing = [f for f in REQUIRED if not cfg.get(f)]
    if missing:
        sys.exit(
            "❌ 缺少配置项：%s\n"
            "   来源：%s\n"
            "   请运行 setup_mail.sh 生成 config/mail.env，或 export 对应环境变量。"
            % (", ".join(missing), source)
        )

    body, kind = read_body(args)
    try:
        msg = build_message(cfg, args.subject, body, args.attachment, kind)
    except FileNotFoundError as exc:
        sys.exit("❌ %s" % exc)

    if args.preview:
        out = Path(args.preview).expanduser().resolve()
        out.write_bytes(msg.as_bytes())
        print("📝 预览邮件已写入：%s（未发送）" % out)
        return 0

    try:
        send_message(cfg, msg)
    except (OSError, smtplib.SMTPException) as exc:
        sys.exit("❌ 邮件发送失败：%s" % exc)

    recipients = ", ".join(split_recipients(cfg["to_addr"]))
    att_info = "，附件 %d 个" % len(args.attachment) if args.attachment else ""
    print("✅ 邮件已发送 -> %s（正文：%s%s）" % (recipients, kind, att_info))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())