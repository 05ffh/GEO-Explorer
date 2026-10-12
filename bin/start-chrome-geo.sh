#!/bin/bash
# 启动 GEO 项目的调试 Chrome —— 供 CDP 采集 OTA 页面 / 调研平台调性
#
# 用法：cd "<repo>" && bash bin/start-chrome-geo.sh
# 与象往项目（端口 9222 / google-chrome-debug）隔离：本脚本用端口 9223 + google-chrome-geo，两者可同时运行。
#
# 可用环境变量覆盖：
#   CHROME_START_URLS   空格分隔的起始 URL
#   GEO_CHROME_PORT     调试端口（默认 9223）

set -e

DEBUG_PORT="${GEO_CHROME_PORT:-9223}"
CONFIG_DIR="$HOME/.config/google-chrome-geo"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_DIR"

# 默认打开的 OTA 页面（甲方相关）。可用 CHROME_START_URLS 覆盖。
if [ -n "${CHROME_START_URLS:-}" ]; then
    read -r -a START_URLS <<< "$CHROME_START_URLS"
else
    START_URLS=(
        "https://hotels.ctrip.com/hotels/429558.html"   # 携程·福州香格里拉
        "https://hotel.meituan.com/"                    # 美团酒店
        "https://www.fliggy.com/"                       # 飞猪
        "https://www.ly.com/hotel/"                     # 同程
    )
fi

echo "======================================"
echo "GEO 调试 Chrome  (端口 $DEBUG_PORT)"
echo "  工作目录: $PROJECT_DIR"
echo "  配置目录: $CONFIG_DIR"
echo "======================================"
echo ""

# 1. 关闭旧的 GEO Chrome（只杀本端口，不动象往的 9222）
if pgrep -f "chrome.*--remote-debugging-port=$DEBUG_PORT" > /dev/null 2>&1; then
    echo "关闭旧 GEO Chrome..."
    pkill -9 -f "chrome.*--remote-debugging-port=$DEBUG_PORT" || true
    sleep 2
fi

# 2. 配置目录
mkdir -p "$CONFIG_DIR"

# 3. 启动
# --ozone-platform=wayland: 绕 WSLg 的 XWayland，避免光标不可见
nohup google-chrome \
  --remote-debugging-port=$DEBUG_PORT \
  --user-data-dir="$CONFIG_DIR" \
  --no-first-run \
  --no-default-browser-check \
  --disable-gpu \
  --disable-gpu-sandbox \
  --ozone-platform=wayland \
  "${START_URLS[@]}" \
  > /tmp/chrome_geo.log 2>&1 &

echo "Chrome PID: $!"
echo ""

# 4. 等待就绪
for i in {1..15}; do
    if curl -s "http://localhost:$DEBUG_PORT/json/version" > /dev/null 2>&1; then
        # 写 DevToolsActivePort（部分 CDP 工具读它）
        mkdir -p "$CONFIG_DIR/Default"
        BROWSER_WS=$(curl -s "http://localhost:$DEBUG_PORT/json/version" | jq -r '.webSocketDebuggerUrl' | sed 's|ws://[^:]*:[0-9]*/||')
        printf '%s\n%s\n' "$DEBUG_PORT" "$BROWSER_WS" > "$CONFIG_DIR/Default/DevToolsActivePort"

        echo "✓ GEO Chrome 就绪"
        echo "  CDP:  http://localhost:$DEBUG_PORT/json/version"
        echo "  CDP 脚本示例: python3 <脚本>  （WebSocket 握手需 suppress_origin=True）"
        echo "  日志: tail -f /tmp/chrome_geo.log"
        echo "  停止: pkill -f 'chrome.*remote-debugging-port=$DEBUG_PORT'"
        exit 0
    fi
    echo "等待中... ($i/15)"
    sleep 2
done

echo "✗ 启动失败，查看 /tmp/chrome_geo.log"
exit 1
