# Anima Bot

LLM-powered Minecraft bot using Python for decision-making and Node.js/Mineflayer for game control.

## Architecture

```
┌─────────────────┐    WebSocket    ┌──────────────────┐
│   Python Brain  │ ◄─────────────► │  Minecraft Bot   │
│  (LLM Control)  │                 │   (Mineflayer)   │
└─────────────────┘                 └──────────────────┘
       Port 8000                           Game Server
```

- **Python Agent**: FastAPI server + LLM brain that makes decisions
- **Node.js Bot**: Mineflayer bot that executes commands in Minecraft
- **Communication**: WebSocket connection between Python and Node.js

## Requirements

My versions:
- Python 3.12
- Node.js 22
- Minecraft Java Edition server (localhost or remote)

## Installation

1. Clone the repository:
```bash
cd anima-bot
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Install Node.js dependencies:
```bash
cd mineflayer
npm install
cd ..
```
> canvas 是一个 需要编译原生 C++ 代码 的模块，依赖系统级库。你可以安装 Visual Studio 的 “使用 C++ 的桌面开发” 工作负载。
> puppeteer 需要下载 Chromium，你可以设置一个国内镜像 $env:PUPPETEER_DOWNLOAD_HOST="https://npmmirror.com/mirrors/puppeteer"。但这个也挺慢的，我硬等了半个小时。

## Configuration

Edit `.env` file:

```bash
MINECRAFT_HOST=localhost
MINECRAFT_PORT=25565
BOT_USERNAME=animabot

# LLM Configuration
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://llmapi.paratera.com/v1/

CHAT_MODEL_NAME=Qwen3-VL-30B-A3B-Instruct
# Qwen3-VL-235B-A22B-Instruct 这个更高级，但先用便宜的
CODE_MODEL_NAME=Qwen3-Coder-Plus

# Prompt Paths
PROMPT_PATH=agent/prompts
```

## Running

You need two terminal windows:

**Terminal 1 - Start the Python brain:**
```bash
python -m agent.core
```

**Terminal 2 - Start the Minecraft bot:**
```bash
node mineflayer/index.js
```

## Project Structure

```
anima-bot/
├── agent/
│   ├── core.py           # Main agent entry point
│   ├── brain.py          # Decision-making logic
│   └── capabilities/     # Agent capabilities (chat, etc.)
├── interfaces/
│   ├── server.py         # FastAPI WebSocket server
│   └── protocol.py       # Communication protocol
├── mineflayer/
│   ├── index.js          # Mineflayer bot entry point
│   ├── lib/              # Observation and action libraries
│   └── package.json      # Node.js dependencies
└── .env                  # Configuration file
```

## How It Works

1. **Observation**: Mineflayer bot observes game events (chat, inventory, entities)
2. **Communication**: Events sent to Python brain via WebSocket
3. **Decision**: LLM processes events and generates actions
4. **Execution**: Bot executes JavaScript code in Minecraft

## Adding Capabilities

Create a new capability in `agent/capabilities/`:

```python
from agent.capabilities.base import Capability

class MyCapability(Capability):
    async def can_handle(self, event):
        # Return (can_process: bool, is_exclusive: bool)
        return True, False

    async def run(self, event):
        # Return decision dict
        return {'type': 'talk', 'content': 'Hello'}
```

Register in `agent/brain.py`:
```python
self.caps = [
    ChatCapability(),
    MyCapability(),  # Add here
]
```

## Troubleshooting

**Bot fails to connect**: Check `MINECRAFT_HOST` and `MINECRAFT_PORT` in `.env`

**WebSocket connection fails**: Ensure Python agent is running before starting the Mineflayer bot

**LLM errors**: Verify `OPENAI_API_KEY` and `OPENAI_BASE_URL` are correct

## License

MIT
