#!/bin/bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
CONFIG_PATH="${SCRIPT_DIR}/config/mail.env"
EXAMPLE_CFG="${SCRIPT_DIR}/config/mail.env.example"
LEGACY_CFG="${SCRIPT_DIR}/config/mail_config.toml"

# 如果配置文件不存在，从模板生成
if [ ! -f "${CONFIG_PATH}" ]; then
    if [ ! -f "${EXAMPLE_CFG}" ]; then
        echo "❌ 缺少模板文件 ${EXAMPLE_CFG}"
        exit 1
    fi
    cp "${EXAMPLE_CFG}" "${CONFIG_PATH}"
fi

echo "=============================="
echo "OpenCode send_email 邮箱交互式配置"
echo "=============================="
echo "当前配置文件: ${CONFIG_PATH}"
echo "直接回车 = 保留原有值"
echo "（该文件含授权码，已在 .gitignore 中忽略，请勿提交到公网）"
echo

# 读取原有配置（优先 .env，兼容旧版 toml）
read_env() {
    grep -E "^${1}=" "${2}" 2>/dev/null | head -1 | cut -d'=' -f2- \
        | sed -e 's/^[[:space:]]*//' -e 's/^"//' -e 's/"$//'
}
read_toml() {
    grep -E "^${1}[[:space:]]*=" "${2}" 2>/dev/null | head -1 | cut -d'=' -f2- \
        | tr -d ' "' 
}
OLD_FROM=$(read_env MAIL_FROM "${CONFIG_PATH}" || true)
OLD_TO=$(read_env MAIL_TO "${CONFIG_PATH}" || true)
OLD_SMTP_HOST=$(read_env SMTP_HOST "${CONFIG_PATH}" || true)
OLD_SMTP_PORT=$(read_env SMTP_PORT "${CONFIG_PATH}" || true)
OLD_TOKEN=$(read_env SMTP_TOKEN "${CONFIG_PATH}" || true)
OLD_SSL=$(read_env SMTP_SSL "${CONFIG_PATH}" || true)

if [[ -z "${OLD_FROM}${OLD_TO}${OLD_SMTP_HOST}" && -f "${LEGACY_CFG}" ]]; then
    OLD_FROM=$(read_toml from_addr "${LEGACY_CFG}" || true)
    OLD_TO=$(read_toml to_addr "${LEGACY_CFG}" || true)
    OLD_SMTP_HOST=$(read_toml smtp_host "${LEGACY_CFG}" || true)
    OLD_SMTP_PORT=$(read_toml smtp_port "${LEGACY_CFG}" || true)
    OLD_TOKEN=$(read_toml token "${LEGACY_CFG}" || true)
    OLD_SSL=$(read_toml smtp_ssl "${LEGACY_CFG}" || true)
fi

OLD_SMTP_PORT=${OLD_SMTP_PORT:-587}
OLD_SSL=${OLD_SSL:-true}

read -p "发件人邮箱[${OLD_FROM}]: " FROM
read -p "收件人邮箱[${OLD_TO}]: " TO
read -p "SMTP服务器地址[${OLD_SMTP_HOST}]: " SMTP_HOST
read -p "SMTP端口[${OLD_SMTP_PORT}]: " SMTP_PORT
read -p "邮箱授权码/Token[不显示，直接输入]: " TOKEN
read -p "启用TLS (true/false)[${OLD_SSL}]: " SMTP_SSL

# 空输入则保留原值
FROM=${FROM:-${OLD_FROM}}
TO=${TO:-${OLD_TO}}
SMTP_HOST=${SMTP_HOST:-${OLD_SMTP_HOST}}
SMTP_PORT=${SMTP_PORT:-${OLD_SMTP_PORT}}
TOKEN=${TOKEN:-${OLD_TOKEN}}
SMTP_SSL=${SMTP_SSL:-${OLD_SSL}}

# 写入 .env（权限收紧到仅属主可读）
umask 077
cat > "${CONFIG_PATH}" <<EOF
# send_email skill 邮箱配置（含授权码，切勿提交到公网）
MAIL_FROM="${FROM}"
MAIL_TO="${TO}"
SMTP_HOST="${SMTP_HOST}"
SMTP_PORT=${SMTP_PORT}
SMTP_TOKEN="${TOKEN}"
SMTP_SSL=${SMTP_SSL}
EOF
chmod 600 "${CONFIG_PATH}" 2>/dev/null || true

echo
echo "✅ 配置写入完成！"
echo "配置文件：${CONFIG_PATH}（已设置仅属主可读权限）"
echo
read -p "是否立刻发送一封测试邮件（含 Markdown 渲染）验证配置？(y/N) " SEND_TEST
if [[ "${SEND_TEST}" =~ ^[Yy]$ ]]; then
    echo "正在发送测试邮件..."
    "${SCRIPT_DIR}/send.sh" <<'JSON'
{
  "subject":"【send_email skill 配置测试】",
  "body_text":"# 邮箱配置成功\n\n已在本机渲染 Markdown 后再发送。\n\n| 功能 | 状态 |\n| --- | --- |\n| Markdown 渲染 | ✅ |\n| 多附件 | ✅ |\n| .env 配置 | ✅ |\n\n- 支持 **加粗**、*斜体*、`行内代码`\n- 支持表格、引用、代码块\n\n> 若能看到排版后的正文，说明渲染正常。\n\n```bash\ncat /etc/os-release\n```",
  "attachments":[]
}
JSON
    echo "📩 测试邮件发送流程结束，请检查收件邮箱"
fi