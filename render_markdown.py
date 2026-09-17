#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_markdown.py — 在本机把 Markdown 渲染成邮件友好的 HTML。

设计参考：多数邮箱客户端不会渲染 Markdown，因此在发送前于本机渲染为 HTML，
邮件中同时附带纯文本（Markdown 源码）作为降级显示。

优先使用已安装的 `markdown` / `markdown2` 扩展渲染；两者都不可用时，回退到
内置的轻量解析器（无第三方依赖，支持标题/列表/表格/代码块/引用/链接等）。

命令行用法：
    python3 render_markdown.py report.md                 # 输出 HTML 片段
    python3 render_markdown.py report.md -o report.html  # 写入文件
    python3 render_markdown.py report.md --no-style      # 不带 CSS
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

try:  # 可选：功能更全的 markdown 渲染器
    import markdown as _MD_LIB  # type: ignore
except ImportError:  # pragma: no cover
    try:
        import markdown2 as _MD_LIB  # type: ignore
    except ImportError:
        _MD_LIB = None

try:  # 可选：代码块语法高亮
    import pygments  # noqa: F401
    from pygments import highlight as _pyg_highlight
    from pygments.formatters import HtmlFormatter as _PygFormatter
    from pygments.lexers import get_lexer_by_name as _pyg_lexer

    _HAS_PYGMENTS = True
except ImportError:  # pragma: no cover
    _HAS_PYGMENTS = False


# --------------------------------------------------------------------------- #
# 邮件友好的内联 CSS（浅色、窄栏、移动端友好）
# --------------------------------------------------------------------------- #
EMAIL_CSS = """
.md-body {
  margin: 0;
  padding: 20px;
  background: #ffffff;
  color: #24292f;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
               "Hiragino Sans GB", "Microsoft YaHei", Helvetica, Arial, sans-serif;
  font-size: 15px;
  line-height: 1.7;
  max-width: 860px;
}
.md-body h1, .md-body h2, .md-body h3,
.md-body h4, .md-body h5, .md-body h6 {
  margin: 22px 0 12px;
  font-weight: 600;
  line-height: 1.3;
  color: #1f2328;
}
.md-body h1 { font-size: 24px; border-bottom: 1px solid #d8dee4; padding-bottom: 8px; }
.md-body h2 { font-size: 20px; border-bottom: 1px solid #eaeef2; padding-bottom: 6px; }
.md-body h3 { font-size: 17px; }
.md-body h4 { font-size: 15px; }
.md-body p { margin: 10px 0; }
.md-body a { color: #0969da; text-decoration: none; }
.md-body a:hover { text-decoration: underline; }
.md-body strong { font-weight: 600; }
.md-body code {
  background: #f6f8fa;
  border: 1px solid #eaeef2;
  border-radius: 4px;
  padding: 1px 5px;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace;
  font-size: 13px;
}
.md-body pre {
  background: #f6f8fa;
  border: 1px solid #eaeef2;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}
.md-body pre code {
  background: transparent;
  border: 0;
  padding: 0;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
}
.md-body blockquote {
  margin: 12px 0;
  padding: 2px 14px;
  color: #57606a;
  border-left: 4px solid #d0d7de;
  background: #f6f8fa;
}
.md-body ul, .md-body ol { margin: 10px 0; padding-left: 26px; }
.md-body li { margin: 4px 0; }
.md-body table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 14px; }
.md-body th, .md-body td { border: 1px solid #d0d7de; padding: 7px 11px; text-align: left; }
.md-body th { background: #f6f8fa; font-weight: 600; }
.md-body tr:nth-child(even) td { background: #fafbfc; }
.md-body hr { border: 0; border-top: 1px solid #d8dee4; margin: 20px 0; }
.md-body img { max-width: 100%; height: auto; }
.md-body .codehilite pre, .md-body pre.codehilite { background: #f6f8fa; }
""".strip()


# --------------------------------------------------------------------------- #
# 内置轻量 Markdown 解析（无第三方依赖时的回退实现）
# --------------------------------------------------------------------------- #
def _inline(md: str) -> str:
    out = html.escape(md, quote=False)
    out = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img src="\2" alt="\1" style="max-width:100%"/>', out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", out)
    return out


def _render_code(code: str, lang: str) -> str:
    if lang and _HAS_PYGMENTS:
        try:
            lexer = _pyg_lexer(lang)
            return _pyg_highlight(code, lexer, _PygFormatter(cssclass="codehilite"))
        except Exception:
            pass
    return '<pre><code>' + html.escape(code, quote=False) + "</code></pre>"


def _cells(row: str) -> list:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


def _is_table_start(lines: list, i: int) -> bool:
    if i + 1 >= len(lines) or "|" not in lines[i]:
        return False
    sep = lines[i + 1].strip()
    return bool(re.match(r"^\|?[\s:|-]*-[\s:|-]*\|[\s:|-]*$", sep))


def _render_table(lines: list, i: int):
    header = _cells(lines[i])
    i += 2
    rows = []
    while i < len(lines) and lines[i].strip() and "|" in lines[i]:
        rows.append(_cells(lines[i]))
        i += 1
    out = ["<table>", "<thead><tr>"]
    out += ["<th>%s</th>" % _inline(c) for c in header]
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>" + "".join("<td>%s</td>" % _inline(c) for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out), i


def _is_block_start(lines: list, i: int) -> bool:
    line = lines[i]
    if re.match(r"^\s*```", line):
        return True
    if re.match(r"^\s{0,3}#{1,6}\s+", line):
        return True
    if re.match(r"^\s*([-*_])\1{2,}\s*$", line):
        return True
    if re.match(r"^\s*>", line):
        return True
    if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
        return True
    return _is_table_start(lines, i)


def _build_list(items: list, base: int) -> str:
    ordered = items[0][1]
    tag = "ol" if ordered else "ul"
    parts = ["<%s>" % tag]
    k = 0
    while k < len(items):
        indent, _ordered, text = items[k]
        if indent > base:
            j = k
            while j < len(items) and items[j][0] > base:
                j += 1
            parts.append(_build_list(items[k:j], min(x[0] for x in items[k:j])))
            k = j
            continue
        parts.append("<li>%s" % _inline(text))
        if k + 1 < len(items) and items[k + 1][0] > base:
            j = k + 1
            while j < len(items) and items[j][0] > base:
                j += 1
            parts.append(_build_list(items[k + 1:j], min(x[0] for x in items[k + 1:j])))
            k = j
        parts.append("</li>")
        k += 1
    parts.append("</%s>" % tag)
    return "".join(parts)


def _render_list(lines: list, i: int):
    items = []
    first_indent = None
    first_ordered = None
    while i < len(lines):
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
        if not m:
            break
        indent = len(m.group(1))
        ordered = m.group(2) not in "-*+"
        if first_indent is None:
            first_indent, first_ordered = indent, ordered
        elif indent == first_indent and ordered != first_ordered:
            break  # 同层级标记类型变化（如无序切有序），另起一个列表
        items.append((indent, ordered, m.group(3)))
        i += 1
    base = min(x[0] for x in items)
    return _build_list(items, base), i


def _convert_builtin(md: str) -> str:
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]

        fence = re.match(r"^\s*```\s*([\w+#.-]*)\s*$", line)
        if fence:
            lang = fence.group(1)
            i += 1
            code = []
            while i < n and not re.match(r"^\s*```\s*$", lines[i]):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(_render_code("\n".join(code), lang))
            continue

        if not line.strip():
            i += 1
            continue

        if re.match(r"^\s*([-*_])\1{2,}\s*$", line):
            out.append("<hr/>")
            i += 1
            continue

        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if heading:
            level = min(len(heading.group(1)) + 1, 6)
            out.append("<h%d>%s</h%d>" % (level, _inline(heading.group(2)), level))
            i += 1
            continue

        if _is_table_start(lines, i):
            table, i = _render_table(lines, i)
            out.append(table)
            continue

        if re.match(r"^\s*>", line):
            quote = []
            while i < n and re.match(r"^\s*>", lines[i]):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % _convert_builtin("\n".join(quote)))
            continue

        if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            lst, i = _render_list(lines, i)
            out.append(lst)
            continue

        para = [line.strip()]
        i += 1
        while i < n and lines[i].strip() and not _is_block_start(lines, i):
            para.append(lines[i].strip())
            i += 1
        out.append("<p>%s</p>" % "<br/>".join(_inline(x) for x in para))

    return "\n".join(out)


def _convert(md: str) -> str:
    if _MD_LIB is not None:
        extensions = ["extra", "tables", "fenced_code", "sane_lists"]
        if _HAS_PYGMENTS:
            extensions.append("codehilite")
        try:
            return _MD_LIB.markdown(md, extensions=extensions, output_format="html5")
        except Exception:
            pass
    return _convert_builtin(md)


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #
def render_markdown_to_html(md: str, with_style: bool = True) -> str:
    """把 Markdown 文本渲染为邮件 HTML。"""
    body = _convert(md).strip()
    if not with_style:
        return body
    return '<div class="md-body">\n<style type="text/css">\n%s\n</style>\n%s\n</div>' % (
        EMAIL_CSS,
        body,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="把 Markdown 渲染为邮件 HTML")
    parser.add_argument("input", help="Markdown 文件路径，'-' 表示标准输入")
    parser.add_argument("-o", "--output", help="输出 HTML 文件路径（默认打印到标准输出）")
    parser.add_argument("--no-style", action="store_true", help="不包含内联 CSS")
    args = parser.parse_args()

    if args.input == "-":
        md = sys.stdin.read()
    else:
        md = Path(args.input).read_text(encoding="utf-8")

    html_out = render_markdown_to_html(md, with_style=not args.no_style)
    if args.output:
        Path(args.output).write_text(html_out, encoding="utf-8")
        print("✅ 已渲染：%s" % args.output)
    else:
        print(html_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())