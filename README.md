# Claude Code × NVIDIA NIM

Use Claude Code with any AI model from NVIDIA — for free.

NVIDIA gives you free API credits to run powerful open-source models like DeepSeek, Llama, Mistral, and more. This tool connects Claude Code to those models in one command.

## Quick start

**1. Get a free NVIDIA API key**

Go to [build.nvidia.com](https://build.nvidia.com), create an account, and copy your API key.

**2. Install**

```bash
git clone https://github.com/Symbioose/claude-code-nvidia
cd free-claude
cp .env.example .env
```

Open `.env` and paste your API key:

```
NVIDIA_API_KEY=nvapi-your-key-here
```

**3. Add a shortcut command**

Instead of navigating to the folder every time, add a `clauden` command to your terminal:

```bash
echo 'alias clauden="(cd ~/path/to/free-claude && ./start.sh)"' >> ~/.zshrc
source ~/.zshrc
```

Now you can launch it from anywhere by just typing `clauden`.

**4. Run**

```bash
clauden
```

Claude Code opens and uses your NVIDIA models.

## Choosing your models

You can assign a different model to each tier in `.env`:

```
MODEL_OPUS=deepseek-ai/deepseek-v4-pro      # most powerful — complex tasks
MODEL_SONNET=deepseek-ai/deepseek-r1        # balanced — everyday coding
MODEL_HAIKU=meta/llama-3.3-70b-instruct     # fastest — quick tasks
```

Pick any model from [build.nvidia.com/models](https://build.nvidia.com/models). The only requirement is that it supports **tool calling**.

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A free NVIDIA account
