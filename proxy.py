#!/usr/bin/env python3
"""
Proxy: Anthropic API format → OpenAI API format (NVIDIA NIM)
Usage: python proxy.py [port]
"""

import json
import sys
import uuid
import os
from pathlib import Path
import requests
from flask import Flask, request, jsonify, Response, stream_with_context

# Load .env from same directory as this script
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

app = Flask(__name__)

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

MODEL_OPUS   = os.environ.get("MODEL_OPUS",   "deepseek-ai/deepseek-v4-pro")
MODEL_SONNET = os.environ.get("MODEL_SONNET", MODEL_OPUS)
MODEL_HAIKU  = os.environ.get("MODEL_HAIKU",  MODEL_SONNET)

ANTHROPIC_MODEL_MAP = {
    "claude-opus-4-7":         MODEL_OPUS,
    "claude-sonnet-4-6":       MODEL_SONNET,
    "claude-haiku-4-5-20251001": MODEL_HAIKU,
    "opus":                    MODEL_OPUS,
    "sonnet":                  MODEL_SONNET,
    "haiku":                   MODEL_HAIKU,
}


def to_openai_messages(messages, system=None):
    result = []
    if system:
        if isinstance(system, list):
            system = " ".join(b.get("text", "") for b in system if b.get("type") == "text")
        result.append({"role": "system", "content": system})

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        # content is a list of blocks
        text_parts = []
        tool_calls = []
        tool_results = []

        for block in content:
            t = block.get("type")
            if t == "text":
                text_parts.append(block["text"])
            elif t == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block.get("input", {}))
                    }
                })
            elif t == "tool_result":
                tool_content = block.get("content", "")
                if isinstance(tool_content, list):
                    tool_content = " ".join(b.get("text", "") for b in tool_content if b.get("type") == "text")
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": block["tool_use_id"],
                    "content": tool_content
                })

        if tool_calls:
            result.append({
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else None,
                "tool_calls": tool_calls
            })
        elif text_parts:
            result.append({"role": role, "content": "\n".join(text_parts)})

        result.extend(tool_results)

    return result


def to_openai_tools(tools):
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {})
            }
        }
        for t in tools
    ]


def to_anthropic_response(oai, model):
    choice = oai["choices"][0]
    msg = choice["message"]
    content = []

    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})

    for tc in msg.get("tool_calls") or []:
        try:
            inp = json.loads(tc["function"]["arguments"])
        except Exception:
            inp = {}
        content.append({
            "type": "tool_use",
            "id": tc["id"],
            "name": tc["function"]["name"],
            "input": inp
        })

    stop_map = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}
    usage = oai.get("usage", {})

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model,
        "stop_reason": stop_map.get(choice.get("finish_reason", "stop"), "end_turn"),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0)
        }
    }


@app.route("/v1/messages", methods=["POST"])
def messages():
    body = request.get_json()
    model = ANTHROPIC_MODEL_MAP.get(body.get("model", ""), DEFAULT_MODEL)
    stream = body.get("stream", False)

    oai_body = {
        "model": model,
        "messages": to_openai_messages(body.get("messages", []), body.get("system")),
        "max_tokens": body.get("max_tokens", 4096),
        "stream": stream,
    }
    if body.get("temperature") is not None:
        oai_body["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        oai_body["top_p"] = body["top_p"]
    if body.get("stop_sequences"):
        oai_body["stop"] = body["stop_sequences"]

    tools = to_openai_tools(body.get("tools"))
    if tools:
        oai_body["tools"] = tools
        tc = body.get("tool_choice")
        if tc:
            if isinstance(tc, dict) and tc.get("type") == "tool":
                oai_body["tool_choice"] = {"type": "function", "function": {"name": tc["name"]}}
            elif isinstance(tc, dict) and tc.get("type") == "any":
                oai_body["tool_choice"] = "required"
            elif isinstance(tc, dict):
                oai_body["tool_choice"] = tc.get("type", "auto")

    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }

    if stream:
        def generate():
            msg_id = f"msg_{uuid.uuid4().hex[:24]}"
            yield f"event: message_start\ndata: {json.dumps({'type':'message_start','message':{'id':msg_id,'type':'message','role':'assistant','content':[],'model':model,'stop_reason':None,'stop_sequence':None,'usage':{'input_tokens':0,'output_tokens':0}}})}\n\n"
            yield f"event: content_block_start\ndata: {json.dumps({'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}})}\n\n"
            yield f"event: ping\ndata: {json.dumps({'type':'ping'})}\n\n"

            resp = requests.post(f"{NVIDIA_BASE_URL}/chat/completions", headers=headers, json=oai_body, stream=True)
            out_tokens = 0

            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if not decoded.startswith("data: "):
                    continue
                data = decoded[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"]
                    if delta.get("content"):
                        out_tokens += 1
                        yield f"event: content_block_delta\ndata: {json.dumps({'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':delta['content']}})}\n\n"
                except Exception:
                    pass

            yield f"event: content_block_stop\ndata: {json.dumps({'type':'content_block_stop','index':0})}\n\n"
            yield f"event: message_delta\ndata: {json.dumps({'type':'message_delta','delta':{'stop_reason':'end_turn','stop_sequence':None},'usage':{'output_tokens':out_tokens}})}\n\n"
            yield f"event: message_stop\ndata: {json.dumps({'type':'message_stop'})}\n\n"

        return Response(stream_with_context(generate()), content_type="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    resp = requests.post(f"{NVIDIA_BASE_URL}/chat/completions", headers=headers, json=oai_body)
    return jsonify(to_anthropic_response(resp.json(), model))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": DEFAULT_MODEL})


if __name__ == "__main__":
    if not NVIDIA_API_KEY:
        print("Error: NVIDIA_API_KEY env var not set")
        sys.exit(1)

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    print(f"Proxy running on http://localhost:{port}")
    print(f"\nConfigure Claude Code:")
    print(f"  export ANTHROPIC_BASE_URL=http://localhost:{port}")
    print(f"  export ANTHROPIC_API_KEY=not-used")
    print(f"  export ANTHROPIC_CUSTOM_MODEL_OPTION={DEFAULT_MODEL}")
    print(f"  export ANTHROPIC_DEFAULT_HAIKU_MODEL={DEFAULT_MODEL}")
    print(f"  export ANTHROPIC_DEFAULT_SONNET_MODEL={DEFAULT_MODEL}")
    print(f"  export ANTHROPIC_DEFAULT_OPUS_MODEL={DEFAULT_MODEL}")
    print(f"  export CLAUDE_CODE_SUBAGENT_MODEL={DEFAULT_MODEL}")
    app.run(host="0.0.0.0", port=port, debug=False)
