#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env
set -a
source "$SCRIPT_DIR/.env"
set +a

# Start proxy in background
echo "Starting proxy on port $PORT..."
uv run "$SCRIPT_DIR/proxy.py" "$PORT" &
PROXY_PID=$!

# Wait for proxy to be ready
for i in {1..10}; do
  if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
    echo "Proxy ready"
    break
  fi
  sleep 0.5
done

echo "Launching Claude Code via NVIDIA NIM (opus=$MODEL_OPUS, sonnet=$MODEL_SONNET, haiku=$MODEL_HAIKU)..."
export ANTHROPIC_BASE_URL="http://localhost:$PORT"
export ANTHROPIC_API_KEY="not-used"
export ANTHROPIC_CUSTOM_MODEL_OPTION="$MODEL_OPUS"
export ANTHROPIC_CUSTOM_MODEL_OPTION_NAME="NVIDIA NIM"
export ANTHROPIC_DEFAULT_OPUS_MODEL="$MODEL_OPUS"
export ANTHROPIC_DEFAULT_SONNET_MODEL="$MODEL_SONNET"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="$MODEL_HAIKU"
export CLAUDE_CODE_SUBAGENT_MODEL="$MODEL_HAIKU"
# Use isolated config dir to avoid conflict with claude.ai session
CLAUDE_CONFIG_DIR="$SCRIPT_DIR/.claude-nvidia" claude "$@"

# Kill proxy when Claude Code exits
kill $PROXY_PID 2>/dev/null
