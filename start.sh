#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env into local vars only (not exported to current shell)
_load_env() {
  local file="$SCRIPT_DIR/.env"
  while IFS='=' read -r key value; do
    [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
    eval "$key=\"$value\""
  done < "$file"
}
_load_env

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

# Run Claude in an isolated subshell — env vars don't leak back to your terminal
(
  export ANTHROPIC_BASE_URL="http://localhost:$PORT"
  export ANTHROPIC_API_KEY="not-used"
  export ANTHROPIC_CUSTOM_MODEL_OPTION="$MODEL_OPUS"
  export ANTHROPIC_CUSTOM_MODEL_OPTION_NAME="NVIDIA NIM"
  export ANTHROPIC_DEFAULT_OPUS_MODEL="$MODEL_OPUS"
  export ANTHROPIC_DEFAULT_SONNET_MODEL="$MODEL_SONNET"
  export ANTHROPIC_DEFAULT_HAIKU_MODEL="$MODEL_HAIKU"
  export CLAUDE_CODE_SUBAGENT_MODEL="$MODEL_HAIKU"
  CLAUDE_CONFIG_DIR="$SCRIPT_DIR/.claude-nvidia" claude "$@"
)

# Kill proxy when Claude Code exits
kill $PROXY_PID 2>/dev/null
