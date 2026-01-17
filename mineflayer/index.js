require('dotenv').config();
const mineflayer = require('mineflayer');
const WebSocket = require('ws');

// --- 依赖引入 ---
// 这里的 require 只是为了让 node 知道我们要用这些包
// 真正给 eval 用的变量要在 message 回调里定义
const { pathfinder, Movements, goals } = require("mineflayer-pathfinder");
const { plugin: tool } = require("mineflayer-tool");
const { plugin: collectBlock } = require("mineflayer-collectblock");
const { plugin: pvp } = require("mineflayer-pvp");
const { Vec3 } = require("vec3");
const fs = require('fs'); // 错误处理可能需要

// --- 观察层 ---
const obs = require("./lib/observation/base");
const skills = require("./lib/skillLoader");
const OnChat = require("./lib/observation/onChat");
const OnError = require("./lib/observation/onError");
const { Voxels, BlockRecords } = require("./lib/observation/voxels");
const Status = require("./lib/observation/status");
const Inventory = require("./lib/observation/inventory");
const Chests = require("./lib/observation/chests");

// 加载技能库
const { loadControlPrimitives } = require('./lib/primitivesLoader');

// 初始化 Bot
const bot = mineflayer.createBot({
    host: process.env.MINECRAFT_HOST || 'localhost',
    port: process.env.MINECRAFT_PORT ? parseInt(process.env.MINECRAFT_PORT) : 25565,
    username: process.env.BOT_USERNAME || 'animabot'
});

bot.loadPlugin(pathfinder);
bot.loadPlugin(tool);
bot.loadPlugin(collectBlock);
bot.loadPlugin(pvp);

let isBotReady = false;

const ws = new WebSocket('ws://localhost:8000/ws/minecraft');

ws.on('open', () => {
    console.log('Connected to Brain!');
});

bot.once('spawn', () => {
    console.log('Bot Spawned.');

    // 初始化逻辑（需要 version 信息，所以必须在 spawn 后）
    const mcData = require("minecraft-data")(bot.version);
    const movements = new Movements(bot, mcData);
    bot.pathfinder.setMovements(movements);

    skills.inject(bot);

    obs.inject(bot, [OnChat, OnError, Voxels, Status, Inventory, Chests, BlockRecords]);

    bot.primitivesCode = loadControlPrimitives();
    bot.waitTicks = 20;
    bot.chat("/gamerule keepInventory true");

    // 解锁
    isBotReady = true;
    console.log('>>> Bot is ready for commands! <<<');
});

// --- 核心逻辑 ---
ws.on('message', async (data) => {
    if (!isBotReady) {
        console.warn("[Warn] Received command but Bot is not spawned yet. Ignoring.");
        ws.send(JSON.stringify({
            source: 'minecraft',
            type: 'execution_done',
            status: 'error',
            error: 'Bot not ready (still spawning)'
        }));
        return;
    }

    const command = JSON.parse(data);

    if (command.type === 'chat') {
        bot.chat(command.payload);
    }
    else if (command.type === 'run_code') {
        console.log("Executing code...");

        // ============================================================
        //  CONTEXT RECONSTRUCTION (重建 Voyager 上下文环境)
        // ============================================================

        // 1. 准备 mcData 并打补丁 (Voyager 里的黑魔法，必须保留)
        const mcData = require("minecraft-data")(bot.version);
        mcData.itemsByName["leather_cap"] = mcData.itemsByName["leather_helmet"];
        mcData.itemsByName["leather_tunic"] = mcData.itemsByName["leather_chestplate"];
        mcData.itemsByName["leather_pants"] = mcData.itemsByName["leather_leggings"];
        mcData.itemsByName["leather_boots"] = mcData.itemsByName["leather_boots"];
        mcData.itemsByName["lapis_lazuli_ore"] = mcData.itemsByName["lapis_ore"];
        mcData.blocksByName["lapis_lazuli_ore"] = mcData.blocksByName["lapis_ore"];

        // 2. 解构 goals 和其他工具类到当前作用域
        // 这一步至关重要！primitive 代码里会直接用 GoalBlock 而不是 goals.GoalBlock
        const {
            Goal, GoalBlock, GoalNear, GoalXZ, GoalNearXZ, GoalY,
            GoalGetToBlock, GoalLookAtBlock, GoalBreakBlock,
            GoalCompositeAny, GoalCompositeAll, GoalInvert,
            GoalFollow, GoalPlaceBlock
        } = require("mineflayer-pathfinder").goals;

        const { Vec3 } = require("vec3");

        // 3. 设置寻路移动参数
        const movements = new Movements(bot, mcData);
        bot.pathfinder.setMovements(movements);

        // 4. Stuck Detection (防卡死机制) - 从 Voyager 移植
        bot.globalTickCounter = 0;
        bot.stuckTickCounter = 0;
        bot.stuckPosList = [];

        function onTick() {
            bot.globalTickCounter++;
            if (bot.pathfinder.isMoving()) {
                bot.stuckTickCounter++;
                if (bot.stuckTickCounter >= 100) { // 5秒不动算卡死
                    // 简单的防卡死策略：随机传送一下或者跳一下
                    console.log("Stuck detected!");
                    bot.stuckTickCounter = 0;
                    bot.entity.position.add(new Vec3(0, 1, 0)); // 尝试跳脱
                }
            }
        }

        // bot.on("physicTick", onTick); // 开启监听
        bot.on("physicsTick", onTick);

        // 5. 初始化失败计数器 (Primitive 代码里会用到)
        let _craftItemFailCount = 0;
        let _killMobFailCount = 0;
        let _mineBlockFailCount = 0;
        let _placeItemFailCount = 0;
        let _smeltItemFailCount = 0;

        // ============================================================
        //  EXECUTION (执行)
        // ============================================================
        try {
            // 构造要执行的代码字符串。
            // 这里的技巧是：我们不需要在字符串里再次 require 那些库了，
            // 因为 eval 会向上查找，而我们已经在上面定义了 Vec3, GoalBlock 等变量。
            const codePayload = command.payload;

            // Voyager 风格的拼接
            const fullCode = `
                (async () => { 
                    ${bot.primitivesCode} 
                    ; 
                    ${codePayload} 
                })()
            `;

            // 执行！
            await eval(fullCode);

            // 执行成功
            const state = bot.observe ? bot.observe() : {};
            ws.send(JSON.stringify({
                source: 'minecraft', type: 'execution_done', status: 'success', state: state
            }));

        } catch (e) {
            console.error("Eval Error:", e);
            bot.chat(`Error: ${e.message.slice(0, 50)}`); // 游戏里别刷屏

            // 这里可以加入 handleError 逻辑来精确定位行号
            ws.send(JSON.stringify({
                source: 'minecraft', type: 'execution_done', status: 'error', error: e.message, stack: e.stack
            }));
        } finally {
            // 清理监听器，防止内存泄漏或逻辑冲突
            // bot.removeListener("physicTick", onTick);
            bot.removeListener("physicsTick", onTick);
        }
    }
});

// Chat Listener
bot.on('chat', (username, message) => {
    if (username === bot.username) return;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ source: 'minecraft', type: 'chat', content: message, user: username }));
    }
});

bot.on('error', err => console.log('Bot Error:', err));
bot.on('kicked', reason => console.log('Bot Kicked:', reason));