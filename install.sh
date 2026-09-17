#!/bin/bash
# install.sh — 安装/检查 send_email skill 的运行依赖并初始化配置。
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

echo "=============================="
echo "send_email skill 安装检查"
echo "=============================="

# 1. Python 3
if command -v python3 >/dev/null 2>&1; then
    echo "✅ python3: $(python3 --version 2>&1)"
else
    echo "❌ 未找到 python3，请先安装（如 yum install -y python3 / apt install -y python3）"
    exit 1
fi

# 2. jq
if command -v jq >/dev/null 2>&1; then
    echo "✅ jq: $(jq --version 2>&1)"
else
    echo "❌ 未找到 jq，请先安装（如 yum install -y jq / apt install -y jq）"
    exit 1
fi

# 3. 可选：更完善的 Markdown 渲染（缺失则使用内置解析器，功能不受影响）
if python3 -c "import markdown" >/dev/null 2>&1; then
    echo "✅ 可选依赖 markdown 已安装（渲染效果更佳）"
elif python3 -c "import markdown2" >/dev/null 2>&1; then
    echo "✅ 可选依赖 markdown2 已安装（渲染效果更佳）"
else
    echo "ℹ️  未安装 markdown/markdown2，将使用内置轻量渲染器（无需额外依赖）"
    echo "    如需更好效果：python3 -m pip install markdown"
fi

# 4. 赋予脚本执行权限
chmod +x "${SCRIPT_DIR}/send.sh" \
         "${SCRIPT_DIR}/send_mail.py" \
         "${SCRIPT_DIR}/render_markdown.py" \
         "${SCRIPT_DIR}/setup_mail.sh" \
         "${SCRIPT_DIR}/install.sh" 2>/dev/null || true
echo "✅ 脚本执行权限已设置"

# 5. 初始化配置文件（.env）
CONFIG_PATH="${SCRIPT_DIR}/config/mail.env"
EXAMPLE_CFG="${SCRIPT_DIR}/config/mail.env.example"
if [ ! -f "${CONFIG_PATH}" ]; then
    cp "${EXAMPLE_CFG}" "${CONFIG_PATH}"
    chmod 600 "${CONFIG_PATH}" 2>/dev/null || true
    echo "✅ 已从模板生成配置：${CONFIG_PATH}（权限 600）"
else
    echo "✅ 配置文件已存在：${CONFIG_PATH}"
fi

echo
echo "安装完成。下一步：运行 ${SCRIPT_DIR}/setup_mail.sh 交互式填写并测试邮箱。"
echo "安全提示：config/mail.env 含授权码，已在 .gitignore 中忽略。"