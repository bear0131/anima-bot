## Agent

这个是核心代码所在地。

#### core.py

所有 event 的枢纽。主循环 & 执行器，将来这两个职能可能会拆开。

class Agent：整个系统本身。

#### brain.py

负责把事件分发给 capabilities，返回决策。

class Brain：在 core 的 Agent 里初始化，字面意思。

#### schema.py

agent 系统内部的数据格式定义。

class Event：在系统内流通，存储于短期记忆。

> type 的类型应该统一了，希望吧。"chat", "code_run_request", "code_run_done", "error", "system_log"，目前应该是这些。

> 注意机器人发的信息的 source 不是 "minecraft" 而是 "bot"。

> 反正这些协议有必要的话都可以改，只改一个字段还是不麻烦的。

class MCState：游戏状态，包括物品栏、血量、周围实体、周围方块等。

class AgentState：agent 状态，包括 mc state，最近截图，以及理论上是状态机位置的东西。把 js 发的 observation 转换成 mc state 的逻辑在它里面。

class Decision：capability 做的决策。

#### short_memory.py

短期记忆类。包括 event 列表和当前状态。把 event 列表和 state 一块渲染成 llm context 的逻辑在这里。

### capabilities

存能力。

#### base.py

class Capability，抽象类定义。

#### chat_capability.py

闲聊的能力。

> 这里有一段“Payload Debug - 打印完整消息内容”可以用。

### prompts

prompts。

#### persona.txt

描述性格的 system prompt。


## docs

#### ARCHITECTURE_v0.1.0.md

Gemini 生成的 MVP 阶段架构设计，现在很多已不适用。

#### WhatsInEachFile.md

本文件。名字是我瞎起的。设计上这个可能就作为主要开发参考文档了。


## interfaces

python 服务器到别的端的接口。

目前以及短期内，都只有 JS mineflayer 端一个客户端。

#### protocol.py

数据协议。目前是 python 和 js 之间的事情，定了 IncomingEvent 和 OutgoingCommand。

#### server.py

设计上是通用的 websocket 服务器，通过 asyncio.Queue 和 core 通信。

> 但可能将来也不一定有连很多东西的需求，也不一定好改，但就先这样吧。


## mineflayer

主要是从 Voyager 复制来的 JS 库。

index.js 是核心，然后 `control_primitives` 是 voyager 他们封装的函数，`control_primitives_context` 是这些函数塞进 context 里给 llm 看的简化版。


## test

测试用品。目前有一个 mock 的 python 端 server，用来测运行代码的，详见 README-TEST.md。


