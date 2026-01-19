# Anima-Bot JS端测试工具使用指南

## 📖 概述

这是一个用于测试 anima-bot Node.js 端的独立测试工具。它模拟 Python 后端的 WebSocket Server，让你可以在不启动完整 Python 环境的情况下测试 JavaScript 代码执行逻辑。

## 🎯 适用场景

- ✅ 开发和调试 control primitives (mineBlock, craftItem 等)
- ✅ 测试动态代码执行逻辑
- ✅ 验证 Voyager 上下文重建是否正确
- ✅ 快速迭代测试，无需重启整个系统
- ✅ 编写测试套件，批量验证功能

## 🚀 快速开始

### 步骤 1: 启动测试服务器

```bash
cd playground
python test-anima-bot.py
```

你会看到：
```
============================================================
Anima-Bot 测试服务器
============================================================

启动 WebSocket Server
  地址: ws://localhost:8000
  路径: /ws/minecraft

等待 Anima-Bot 连接...
(在另一个终端运行: node anima-bot/mineflayer/index.js)
```

### 步骤 2: 启动 anima-bot (保持默认配置即可)

```bash
cd anima-bot/mineflayer
node index.js
```

**说明**: anima-bot 的 index.js 默认连接 `ws://localhost:8000/ws/minecraft`，正好对应测试服务器。

### 步骤 3: 测试服务器会显示连接成功

```
✓ Anima-Bot 已连接! (/ws/minecraft)
ℹ  输入 'help' 查看可用命令
```

## 🎮 交互命令

### 1. code - 执行 JavaScript 代码

```bash
# 发送聊天
code bot.chat('Hello World');

# 挖矿
code await mineBlock(bot, 'oak_log', 3);

# 合成
code await craftItem(bot, 'oak_planks', 4);

# 复杂操作
code await exploreUntil(bot, 'crafting_table', 32, 32);
```

### 2. file - 运行测试文件

```bash
# 运行单个测试文件
file tests/01-chat.js
file tests/02-mine-block.js
```

### 3. suite - 运行测试套件

```bash
# 运行整个测试目录
suite tests/
```

这会按顺序执行 `tests/` 目录下所有的 `.js` 文件。

### 4. chat - 发送聊天消息

```bash
chat Hello Minecraft!
```

### 5. help - 显示帮助

```bash
help
```

### 6. quit - 退出

```bash
quit
```

## 📁 测试文件结构

```
playground/
├── test-anima-bot.py          # 测试服务器脚本
├── README-TEST.md             # 本文档
└── tests/                     # 测试用例目录
    ├── 01-chat.js            # 聊天测试
    ├── 02-mine-block.js      # 挖矿测试
    ├── 03-craft-item.js      # 合成测试
    └── 04-complex.js         # 复杂综合测试
```

## 📝 测试文件示例

### 简单测试

```javascript
// tests/01-chat.js
bot.chat('Hello from test!');
```

### 挖矿测试

```javascript
// tests/02-mine-block.js
await mineBlock(bot, 'oak_log', 3);
```

### 综合测试

```javascript
// tests/04-complex.js
await exploreUntil(bot, 'oak_log', 32, 32);
await mineBlock(bot, 'oak_log', 3);
await craftItem(bot, 'oak_planks', 4);
bot.chat('Complex test completed!');
```

## 🎨 输出说明

### 成功执行
```
[聊天] Jarvis_MVP: Hello from test!
✓ 代码执行成功
```

### 执行失败
```
✗ 代码执行失败: No block named invalid_block
  堆栈: Error: No block named invalid_block...
```

### 收到消息
```
[聊天] Player: hello
```

## 🔧 高级用法

### 自定义服务器端口

```bash
# 启动测试服务器在 9000 端口
python test-anima-bot.py --port 9000

# 然后修改 anima-bot/mineflayer/index.js
# ws = new WebSocket('ws://localhost:9000/ws/minecraft');
```

### 创建自定义测试

1. 在 `tests/` 目录创建新的 `.js` 文件
2. 编写测试代码
3. 使用 `suite tests/` 或 `file your-test.js` 运行

### 调试技巧

**查看执行状态**:
```javascript
code bot.chat(JSON.stringify(bot.observe()));
```

**查看物品栏**:
```javascript
code console.log(bot.inventory.items());
```

**查看位置**:
```javascript
code bot.chat(`Position: ${bot.entity.position}`);
```

## 🐛 常见问题

### Q: 测试服务器启动失败？
A: 检查端口 8000 是否被占用：
```bash
# Windows
netstat -ano | findstr :8000

# Linux/Mac
lsof -i :8000
```

### Q: anima-bot 连接不上？
A: 确保：
1. 测试服务器先启动
2. anima-bot 的 WebSocket 地址正确
3. 防火墙没有阻止本地连接

### Q: 代码执行超时？
A: 某些操作（如长途寻路）可能需要较长时间，可以：
1. 增加 test-anima-bot.py 中的超时时间
2. 分步执行，不要一次执行太多代码

### Q: 如何测试需要 Python 端逻辑的功能？
A: 这个工具仅测试 JS 端。如果需要测试完整的端到端功能，需要启动真实的 Python 后端。

## 📊 与生产环境的区别

| 特性 | 测试工具 | 生产环境 |
|------|---------|---------|
| WebSocket Server | 测试工具 (Python) | FastAPI 后端 |
| 智能决策 | ❌ 无 | ✅ 有 LLM + Brain |
| 记忆系统 | ❌ 无 | ✅ 有 ChromaDB |
| JS 代码执行 | ✅ 完全相同 | ✅ 完全相同 |
| Control Primitives | ✅ 完全相同 | ✅ 完全相同 |
| 观察层 | ✅ 完全相同 | ✅ 完全相同 |

**结论**: 这个工具专注于验证 JS 端的代码执行是否正确，不涉及 Python 端的决策逻辑。

## 🎓 最佳实践

1. **小步迭代**: 先测试简单功能，再测试复杂功能
2. **独立测试**: 每个测试文件只测试一个功能点
3. **清晰命名**: 测试文件名要有描述性，如 `01-chat.js`
4. **注释说明**: 在测试文件中添加注释说明测试目的
5. **清理环境**: 测试前确保 bot 处于良好状态

## 🚀 下一步

- [ ] 添加更多测试用例到 `tests/` 目录
- [ ] 创建性能测试（大量执行代码）
- [ ] 添加断言库，自动验证结果
- [ ] 集成到 CI/CD 流程

## 📞 支持

如有问题，请查看：
- anima-bot 架构文档: [ARCHITECTURE_v0.1.0.md](../anima-bot/docs/ARCHITECTURE_v0.1.0.md)
- Voyager 原始实现: [Voyager/](../Voyager/)

---

**Happy Testing! 🎉**
