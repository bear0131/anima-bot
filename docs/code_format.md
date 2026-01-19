> 这个文件是 Claude Code 自己写上头了写的，关于 coding capability 生成的东西到底是什么的问题。我看也挺好的，就留着了。

# Anima-Bot 代码格式规范

## 概述

anima-bot 采用与 Voyager 不同的代码执行方式。LLM 生成的代码应该直接是可执行逻辑，而不是完整的函数声明。

## 代码执行流程

### 1. LLM 生成代码

LLM 根据 prompt 生成 JSON 格式响应：

```json
{
  "explain": "解释",
  "plan": "计划",
  "code": "// 直接写可执行逻辑\nconst block = bot.findBlock({...});\nif (block) {\n  await bot.dig(block);\n}"
}
```

### 2. Python 处理

`agent/capabilities/coding.py` 提取 `code` 字段：

```python
code = result_json.get("code", "")
return {
    "type": "code_run_request",
    "content": code,  # 发送给 JS 的代码
    "reason": plan,
}
```

### 3. JavaScript 执行

`mineflayer/index.js` 将代码包装并执行：

```javascript
const code = command.payload;  // 从 Python 接收的代码
const programs = bot.primitivesCode;  // 控制原语

// 包装并执行
await eval("(async () => {" + programs + "\n" + code + "})()");
```

实际执行的代码结构：

```javascript
(async () => {
  // programs (控制原语)
  function mineBlock(bot, type, count = 1) { ... }
  function craftItem(bot, ...) { ... }

  // code (LLM 生成的代码)
  const block = bot.findBlock({
    matching: mcData.blocksByName.oak_log.id,
    maxDistance: 32
  });

  if (block) {
    await bot.dig(block);
  }
})()
```

## 正确的代码格式

### ✅ 正确示例

```javascript
// 直接写可执行逻辑
const blocks = bot.findBlocks({
  matching: mcData.blocksByName.oak_log.id,
  maxDistance: 32,
  count: 3
});

for (const pos of blocks) {
  const block = bot.blockAt(pos);
  if (block) {
    await bot.dig(block);
    bot.chat('Mined an oak log');
  }
}
```

### ❌ 错误示例

```javascript
// 错误：不要声明函数
async function mineWood(bot) {
  const block = bot.findBlock({...});
  await bot.dig(block);
}

// 错误：不要调用函数
await mineWood(bot);
```

## 与 Voyager 的区别

### Voyager 方式

```javascript
// LLM 生成
async function mineWood(bot) { ... }

// Voyager 解析
program_code = "async function mineWood(bot) { ... }"
exec_code = "await mineWood(bot);"

// 执行
eval("(async () => {" + programs + "\n" + program_code + "\n" + exec_code + "})()");
```

### Anima-Bot 方式

```javascript
// LLM 生成
const block = bot.findBlock({...});
await bot.dig(block);

// Anima-Bot 直接执行
eval("(async () => {" + programs + "\n" + code + "})()");
```

## Prompt 要求

在 `agent/prompts/coding_system.txt` 中的关键要求：

1. **DO NOT declare a function** - 不要声明函数
2. **Write executable code directly** - 直接写可执行代码
3. **DO NOT include 'async function' declaration** - 不要包含 async function 声明
4. **Just write the logic directly** - 只写逻辑代码

## 可用的变量和函数

在代码中可以直接使用：

- `bot` - Mineflayer bot 实例
- `mcData` - Minecraft 数据
- `Vec3` - 向量类
- `Goal`, `GoalBlock`, `GoalNear`, 等 - Pathfinder goals
- `mineBlock(bot, name, count)` - 挖矿原语
- `craftItem(bot, name, count)` - 合成原语
- `smeltItem(bot, name, count)` - 熔炼原语
- `placeItem(bot, name, position)` - 放置原语
- `killMob(bot, name, timeout)` - 战斗原语
- `exploreUntil(bot, direction, maxDistance, callback)` - 探索原语

## 测试

运行测试查看代码格式示例：

```bash
cd tests
node test_code_format.js
```

## 常见问题

### Q: 为什么不使用 Voyager 的函数声明方式？

A: anima-bot 采用更简洁的方式，让 LLM 直接生成可执行逻辑，省去了函数声明的复杂性。这对于单次执行的场景更高效。

### Q: 如何复用代码？

A: 通过控制原语（primitives）复用基础操作。复杂的任务可以通过多次调用和组合原语完成。

### Q: 如果需要辅助函数怎么办？

A: 可以在代码中定义局部函数，但不要把它们作为主函数。直接在最外层写执行逻辑。

示例：

```javascript
// 可以定义辅助函数
function findNearestBlock(bot, blockType) {
  return bot.findBlock({
    matching: blockType,
    maxDistance: 32
  });
}

// 但要直接执行逻辑
const logBlock = findNearestBlock(bot, mcData.blocksByName.oak_log.id);
if (logBlock) {
  await bot.dig(logBlock);
}
```
