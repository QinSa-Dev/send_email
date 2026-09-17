#!/bin/bash
# send.sh — agent 调用入口。从标准输入读取 JSON，发送邮件（支持附件）。
#
# 输入 JSON 字段：
#   subject     必填，邮件标题
#   body_file   可选，正文文件路径（支持 ~ 简写；.md 会在本机渲染为 HTML）
#   body_text   可选，直接填入的正文文本（按 Markdown 渲染，可为空串）
#   attachments 可选，附件路径数组，例如 ["~/a.pdf", "/tmp/b.png"]
#
# body_text 非空时优先；否则读取 body_file；两者都为空则发送空正文。
#
# 配置来源（按优先级）：环境变量 > $SEND_EMAIL_CONFIG > config/mail.env
#   > .env > config/mail_config.toml（旧格式）。请勿把真实配置提交到公网。
#
# 示例：
#   ./send.sh <<'JSON'
#   {"subject":"测试","body_text":"# 标题\nhello","attachments":["~/report.pdf"]}
#   JSON
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ 缺少依赖 jq，请先安装（可运行 ${SCRIPT_DIR}/install.sh）" >&2
    exit 1
fi

INPUT=$(cat)
jq_get() { printf '%s' "${INPUT}" | jq -r "$1"; }

SUBJECT=$(jq_get '.subject // empty')
BODY_FILE_RAW=$(jq_get '.body_file // empty')
BODY_TEXT=$(jq_get '.body_text // empty')
ATTACHMENTS_JSON=$(printf '%s' "${INPUT}" | jq -c '.attachments // []')

if [[ -z "${SUBJECT}" ]]; then
    echo "❌ 缺少必填字段 subject" >&2
    exit 1
fi

# 定位配置文件（不存在时交给 send_mail.py 用环境变量兜底并给出提示）
CONFIG_ARG=()
for cand in "${SEND_EMAIL_CONFIG:-}" \
            "${SCRIPT_DIR}/config/mail.env" \
            "${SCRIPT_DIR}/.env" \
            "${SCRIPT_DIR}/config/mail_config.toml"; do
    if [[ -n "${cand}" && -f "${cand}" ]]; then
        CONFIG_ARG=(--config "${cand}")
        break
    fi
done

TMP_MD=""
cleanup() { [[ -n "${TMP_MD}" && -f "${TMP_MD}" ]] && rm -f "${TMP_MD}"; }
trap cleanup EXIT

CMD=(python3 "${SCRIPT_DIR}/send_mail.py" "${CONFIG_ARG[@]}" --subject "${SUBJECT}")

# 正文：优先非空 body_text（Markdown 渲染）；否则读取 body_file
if [[ -n "${BODY_TEXT}" ]]; then
    TMP_MD=$(mktemp /tmp/opencode-mail-body-XXXXXX.md)
    printf '%s\n' "${BODY_TEXT}" > "${TMP_MD}"
    CMD+=(--body-file "${TMP_MD}")
elif [[ -n "${BODY_FILE_RAW}" ]]; then
    CMD+=(--body-file "${BODY_FILE_RAW}")
fi

# 附件（Python 侧负责展开 ~ 与环境变量）
while IFS= read -r item; do
    [[ -n "${item}" ]] && CMD+=(--attachment "${item}")
done < <(printf '%s' "${ATTACHMENTS_JSON}" | jq -r '.[]')

"${CMD[@]}"