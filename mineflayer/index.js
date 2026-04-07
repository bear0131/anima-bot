require('dotenv').config();
const mineflayer = require('mineflayer');
const WebSocket = require('ws');

// ============================================================
//  全局错误处理 - 防止静默崩溃
// ============================================================

// 全局变量引用 (在 ws 初始化后会被赋值)
let globalWs = null;

process.on('unhandledRejection', (reason, promise) => {
    console.error('\n╔════════════════════════════════════════════════════════════╗');
    console.error('║     UNHANDLED PROMISE REJECTION - 进程可能崩溃         ║');
    console.error('╚════════════════════════════════════════════════════════════╝');
    console.error('Promise:', promise);
    console.error('Reason:', reason);
    console.error('Message:', reason?.message || String(reason));
    console.error('Stack:', reason?.stack || 'No stack trace available');
    console.error('Timestamp:', new Date().toISOString());
    console.error('══════════════════════════════════════════════════════════════\n');

    // 发送错误到 WebSocket (如果连接存在)
    if (globalWs && globalWs.readyState === WebSocket.OPEN) {
        try {
            globalWs.send(JSON.stringify({
                source: 'minecraft',
                type: 'critical_error',
                content: {
                    error_type: 'unhandledRejection',
                    reason: reason?.message || String(reason),
                    stack: reason?.stack,
                    timestamp: new Date().toISOString()
                },
                metadata: {}
            }));
        } catch (sendErr) {
            console.error('Failed to send error to WebSocket:', sendErr.message);
        }
    }
});

process.on('uncaughtException', (err) => {
    console.error('\n╔════════════════════════════════════════════════════════════╗');
    console.error('║        UNCAUGHT EXCEPTION - 进程即将退出              ║');
    console.error('╚════════════════════════════════════════════════════════════╝');
    console.error('Error:', err.name);
    console.error('Message:', err.message);
    console.error('Stack:', err.stack);
    console.error('Timestamp:', new Date().toISOString());
    console.error('══════════════════════════════════════════════════════════════\n');

    // 发送错误到 WebSocket (如果连接存在)
    if (globalWs && globalWs.readyState === WebSocket.OPEN) {
        try {
            globalWs.send(JSON.stringify({
                source: 'minecraft',
                type: 'critical_error',
                content: {
                    error_type: 'uncaughtException',
                    message: err.message,
                    stack: err.stack,
                    timestamp: new Date().toISOString()
                },
                metadata: {}
            }));
        } catch (sendErr) {
            console.error('Failed to send error to WebSocket:', sendErr.message);
        }
    }

    // 退出进程以触发 Python 端重启
    console.error('[JS] Exiting due to uncaught exception...');
    process.exit(1);
});

// ============================================================
//  优雅退出处理 - 响应 Python 端的终止信号
// ============================================================

process.on('SIGTERM', async () => {
    console.log('[JS] Received SIGTERM, shutting down gracefully...');

    try {
        // 关闭 Puppeteer browser
        if (browser) {
            console.log('[JS] Closing browser...');
            await browser.close();
        }

        // 关闭 WebSocket 连接
        if (globalWs && globalWs.readyState === WebSocket.OPEN) {
            console.log('[JS] Closing WebSocket...');
            globalWs.close();
        }

        // 退出 Minecraft bot
        if (bot) {
            console.log('[JS] Quitting bot...');
            bot.quit();
        }

        console.log('[JS] Graceful shutdown complete');
        process.exit(0);
    } catch (err) {
        console.error('[JS] Error during shutdown:', err);
        process.exit(1);
    }
});

process.on('SIGINT', async () => {
    console.log('[JS] Received SIGINT, shutting down...');
    // 同 SIGTERM 处理
    process.emit('SIGTERM');
});

// 监控内存使用
let memoryMonitorInterval;
function startMemoryMonitoring() {
    if (memoryMonitorInterval) {
        clearInterval(memoryMonitorInterval);
    }

    memoryMonitorInterval = setInterval(() => {
        const used = process.memoryUsage();
        const rssMB = Math.round(used.rss / 1024 / 1024);
        const heapMB = Math.round(used.heapUsed / 1024 / 1024);
        const heapTotalMB = Math.round(used.heapTotal / 1024 / 1024);
        const externalMB = Math.round(used.external / 1024 / 1024);

        // 每5分钟输出一次内存状态
        console.log(`[Memory Monitor] RSS: ${rssMB}MB | Heap: ${heapMB}MB/${heapTotalMB}MB | External: ${externalMB}MB`);

        // 内存使用超过 2GB 时发出警告
        if (used.rss > 2 * 1024 * 1024 * 1024) {
            console.error('\n╔════════════════════════════════════════════════════════════╗');
            console.error('║            WARNING: CRITICAL HIGH MEMORY USAGE           ║');
            console.error('╚════════════════════════════════════════════════════════════╝');
            console.error(`RSS: ${rssMB}MB exceeds 2GB threshold!`);
            console.error(`Heap: ${heapMB}MB / ${heapTotalMB}MB`);
            console.error(`External: ${externalMB}MB`);
            console.error('This may lead to process crash or OOM!');
            console.error('Consider restarting the bot.');
            console.error('══════════════════════════════════════════════════════════════\n');

            if (globalWs && globalWs.readyState === WebSocket.OPEN) {
                try {
                    globalWs.send(JSON.stringify({
                        source: 'minecraft',
                        type: 'warning',
                        content: {
                            warning_type: 'high_memory',
                            rss_mb: rssMB,
                            heap_mb: heapMB,
                            heap_total_mb: heapTotalMB,
                            external_mb: externalMB,
                            timestamp: new Date().toISOString()
                        },
                        metadata: {}
                    }));
                } catch (sendErr) {
                    console.error('Failed to send warning to WebSocket:', sendErr.message);
                }
            }
        }
    }, 30000); // 每30秒检查一次
}

// ============================================================
//  其他初始化
// ============================================================

// 解析命令行参数
function parseArgs() {
    const args = process.argv.slice(2);
    const parsed = {};
    for (const arg of args) {
        if (arg.startsWith('--')) {
            const [key, value] = arg.slice(2).split('=');
            parsed[key] = value === undefined ? 'true' : value;
        }
    }
    return parsed;
}


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
const { Voxels, BlockRecords, VisibleBlocks } = require("./lib/observation/voxels");
const Status = require("./lib/observation/status");
const Inventory = require("./lib/observation/inventory");
const Chests = require("./lib/observation/chests");

// 加载技能库
const { loadControlPrimitives } = require('./lib/primitivesLoader');

// 初始化 Bot
const bot = mineflayer.createBot({
    host: process.env.MINECRAFT_HOST || 'localhost',
    port: process.env.MINECRAFT_PORT ? parseInt(process.env.MINECRAFT_PORT) : 25565,
    username: process.env.BOT_USERNAME || 'animabot',
    version: '1.18.2'
});

bot.loadPlugin(pathfinder);
bot.loadPlugin(tool);
bot.loadPlugin(collectBlock);
bot.loadPlugin(pvp);

let isBotReady = false;

const ws = new WebSocket('ws://localhost:8000/ws/minecraft');

// 绑定 WebSocket 到全局变量,供错误处理器使用
globalWs = ws;

// 启动内存监控
startMemoryMonitoring();

let browser = null

ws.on('open', () => {
    console.log('Connected to Brain!');
});

bot.once('spawn', async () => {
    console.log('Bot Spawned.');

    const mcData = require("minecraft-data")(bot.version);
    const movements = new Movements(bot, mcData);
    bot.pathfinder.setMovements(movements);

    skills.inject(bot);

    obs.inject(bot, [OnChat, OnError, Voxels, Status, Inventory, Chests, BlockRecords, VisibleBlocks]);

    bot.primitivesCode = loadControlPrimitives();
    bot.waitTicks = 20;
    bot.chat("/gamerule keepInventory true");

    const currentPos = bot.entity.position;
    bot.chat(`/tp animabot ${currentPos.x.toFixed(2)} ${currentPos.y.toFixed(2)} ${currentPos.z.toFixed(2)} 90 0`);
    await bot.waitForTicks(10);
    bot.chat(`/tp animabot ${currentPos.x.toFixed(2)} ${currentPos.y.toFixed(2)} ${currentPos.z.toFixed(2)} 0 0`);

    // 解锁
    isBotReady = true;
    console.log('>>> Bot is ready for commands! <<<');

    // 传当前状态

    setInterval(async () => {
        let snapshotPromise = Promise.resolve();

        // 发送文字状态信息
        snapshotPromise.then(() => {
            try {
                const state = bot.observe();
                ws.send(JSON.stringify({
                    source: 'minecraft',
                    type: 'observation',
                    content: state,  // JSON 字符串
                    timestamp: Date.now(),
                    metadata: {}
                }));
            } catch (e) {
                console.error("Observation error:", e);
                ws.send(JSON.stringify({
                    source: 'minecraft',
                    type: 'observation',
                    content: null,
                    metadata: { error: e.message }
                }));
            }
        });
    }, 500); // 500ms = 0.5秒
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

    if (command.type === 'bot_chat') {
        bot.chat(command.payload);
    } else if (command.type === 'code_run_request') {
        console.log("Executing code...");
        
        const incomingMetadata = command.metadata || {};

        //  Context reconstruction

        // 1. 准备 mcData 并打补丁
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

        // 4. Stuck Detection (防卡死机制)
        /*
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

        bot.on("physicsTick", onTick);
        */

        // 5. 初始化失败计数器 (Primitive 代码里会用到)
        let _craftItemFailCount = 0;
        let _killMobFailCount = 0;
        let _mineBlockFailCount = 0;
        let _placeItemFailCount = 0;
        let _smeltItemFailCount = 0;

        // ============================================================
        //  EXECUTION (执行)
        // ============================================================
        // 6. 等待一点时间，确保世界状态稳定
        await bot.waitForTicks(bot.waitTicks);

        async function runCodeWithTimeout(bot, generatedCode, timeoutMs = 60000) {
            return new Promise(async (resolve, reject) => {
                const timeoutTimer = setTimeout(() => {
                    console.log(`⏰ [超时拦截] 代码运行超过 ${timeoutMs / 1000} 秒，正在强制刹车...`);

                    // 🔴 核心操作：强制掐断 Bot 的一切当前动作，防止它在后台继续发疯
                    try {
                        // 清空寻路目标，停下脚步
                        if (bot.pathfinder) bot.pathfinder.setGoal(null);
                        // 松开所有按键 (前进、跳跃等)
                        bot.clearControlStates();
                        // 停止正在进行的挖矿
                        bot.stopDigging();
                        // 停止可能正在进行的使用物品动作 (如吃东西、拉弓)
                        bot.deactivateItem();
                    } catch (cleanupErr) {
                        // 忽略清理时可能产生的报错
                    }

                    // 拒绝 Promise，抛出超时错误
                    reject(new Error(`Timeout: 代码执行超过了 ${timeoutMs / 1000} 秒被系统强制终止！`));
                }, timeoutMs);

                try {
                    // 2. 将大模型的字符串代码构造成一个 Async 函数
                    // 这相当于 async function(bot, require) { /* 生成的代码 */ }
                    const AsyncFunction = Object.getPrototypeOf(async function () { }).constructor;
                    const aiFunction = new AsyncFunction('bot', 'require', generatedCode);

                    // 3. 开始执行 AI 的代码
                    await aiFunction(bot, require);

                    // 4. 如果代码在 60 秒内顺利执行完了，拆除定时炸弹
                    clearTimeout(timeoutTimer);
                    resolve("代码执行成功");

                } catch (err) {
                    // 如果代码执行过程中自己报错了（比如语法错误），也拆除炸弹并抛出
                    clearTimeout(timeoutTimer);
                    reject(err);
                }
            });
        }

        const code = command.payload;
        const programs = bot.primitivesCode;
        const sandboxInitCode = `
            // 1. 在沙盒内初始化并修补 mcData
            const mcData = require("minecraft-data")(bot.version);
            mcData.itemsByName["leather_cap"] = mcData.itemsByName["leather_helmet"];
            mcData.itemsByName["leather_tunic"] = mcData.itemsByName["leather_chestplate"];
            mcData.itemsByName["leather_pants"] = mcData.itemsByName["leather_leggings"];
            mcData.itemsByName["leather_boots"] = mcData.itemsByName["leather_boots"];
            if (mcData.itemsByName["lapis_ore"]) mcData.itemsByName["lapis_lazuli_ore"] = mcData.itemsByName["lapis_ore"];
            if (mcData.blocksByName["lapis_ore"]) mcData.blocksByName["lapis_lazuli_ore"] = mcData.blocksByName["lapis_ore"];

            // 2. 引入坐标库和所有的寻路 Goal
            const { Vec3 } = require("vec3");
            const {
                Goal, GoalBlock, GoalNear, GoalXZ, GoalNearXZ, GoalY,
                GoalGetToBlock, GoalLookAtBlock, GoalBreakBlock,
                GoalCompositeAny, GoalCompositeAll, GoalInvert,
                GoalFollow, GoalPlaceBlock
            } = require("mineflayer-pathfinder").goals;

            // 3. 初始化 Primitive 技能库需要的全局失败计数器
            let _craftItemFailCount = 0;
            let _killMobFailCount = 0;
            let _mineBlockFailCount = 0;
            let _placeItemFailCount = 0;
            let _smeltItemFailCount = 0;
        `;

        // 🌟 新增了 timeoutMs 参数，默认值为 60000 (60秒)
        async function evaluateCode(code, programs, timeoutMs = 30000) {
            let outputMessages = []; // 用于收集输出

            // 将 report 注入到全局作用域
            global.report = (msg) => {
                if (typeof msg === 'string') {
                    outputMessages.push(msg);
                } else {
                    outputMessages.push(JSON.stringify(msg));
                }
            };

            try {
                // 把声明拼接到最前面
                const fullCode = sandboxInitCode + "\n" + programs + "\n" + code;

                await runCodeWithTimeout(bot, fullCode, timeoutMs);

                return { success: true, messages: outputMessages };

            } catch (error) {
                if (error.message && error.message.includes("Timeout")) {
                    // 动态计算秒数，用于友好的日志提示
                    const timeoutSeconds = Math.floor(timeoutMs / 1000);

                    console.warn(`⚠️ [系统拦截] 任务执行已达 ${timeoutSeconds} 秒上限，正常中止。`);

                    // 动态注入文本
                    outputMessages.push(`[System] ⏳ 任务执行时间超过 ${timeoutSeconds} 秒，已被系统安全中止。已保留当前进度，如未完成请继续下达后续指令。`);

                    return { success: true, messages: outputMessages };
                }

                console.error("❌ 代码运行报错:", error);
                return { success: false, error: error.message, messages: outputMessages };

            } finally {
                delete global.report;
            }
        }

        try {
            const result = await evaluateCode(code, programs);

            if (!result.success) {
                // 执行出错
                console.error("Eval Error:", result.error);
                bot.chat(`Error: ${result.error.message ? result.error.message.slice(0, 50) : result.error}`);

                ws.send(JSON.stringify({
                    source: 'minecraft',
                    type: 'code_run_result',
                    error: result.error.message || result.error,
                    content: result.messages.join('\n') || result.error.stack,
                    metadata: incomingMetadata
                }));
            } else {
                // 执行成功
                console.log("Code executed successfully!");
                ws.send(JSON.stringify({
                    source: 'minecraft',
                    type: 'code_run_result',
                    content: result.messages.join('\n') || "执行完成，无输出。",
                    metadata: incomingMetadata
                }));
            }

            // 等待最后的消息
            await bot.waitForTicks(bot.waitTicks);

        } catch (e) {
            console.error("Execution Error:", e);
            bot.chat(`Error: ${e.message.slice(0, 50)}`);

            ws.send(JSON.stringify({
                source: 'minecraft',
                type: 'code_run_result',
                error: e.message,
                content: e.stack,
                metadata: incomingMetadata
            }));
        } finally {
            // // 清理监听器，防止内存泄漏或逻辑冲突
            // bot.removeListener("physicsTick", onTick);
        }
    }
});

// Chat Listener
bot.on('chat', (username, message) => {
    if (username === bot.username) return;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ source: 'minecraft', type: 'user_chat', content: message, metadata: { user: username } }));
    }
});

bot.on('error', err => {
    console.error('[JS] Bot Error:', err);
    // 严重错误时退出，让 Python 端重启
    if (err.message && (
        err.message.includes('ETIMEDOUT') ||
        err.message.includes('ECONNREFUSED') ||
        err.message.includes('Handshake')
    )) {
        console.error('[JS] Fatal bot error, exiting...');
        process.exit(1);
    }
});
bot.on('kicked', reason => {
    console.error('[JS] Bot Kicked:', reason);
    // 被踢出时退出
    console.error('[JS] Bot was kicked, exiting...');
    process.exit(1);
});