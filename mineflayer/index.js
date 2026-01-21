
require('dotenv').config();
const mineflayer = require('mineflayer');
const WebSocket = require('ws');
const { mineflayer: mineflayerViewer } = require('prismarine-viewer')
const puppeteer = require('puppeteer')

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

    // 注意: 不退出进程,让错误处理继续
    // 但严重错误可能导致进程不稳定,应该记录并重启
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

const argv = parseArgs();
// headless 参数：默认为 true，如果传入 --headless=false 则设为 false
const headlessMode = argv.headless !== 'false';

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

// 绑定 WebSocket 到全局变量,供错误处理器使用
globalWs = ws;

// 启动内存监控
startMemoryMonitoring();

let browser = null
let page = null

ws.on('open', () => {
    console.log('Connected to Brain!');
});

bot.once('spawn', async () => {
    console.log('Bot Spawned.');

    // 启动 Viewer (Web服务器)
    mineflayerViewer(bot, { port: 3007, firstPerson: true });
    console.log('Viewer started on port 3007');

    try {
        // 3. 启动 Puppeteer
        browser = await puppeteer.launch({ headless: headlessMode }); // headless 表示不显示浏览器界面，调试可以设为 false
        page = await browser.newPage();

        // 设置视口大小
        await page.setViewport({ width: 640, height: 480 });

        // 访问 Viewer 页面
        await page.goto('http://localhost:3007');

        // 等待页面加载
        await new Promise(r => setTimeout(r, 2000));

        console.log('Ready to take screenshots!');
    } catch (err) {
        console.error('Failed to start screenshot server.', err);
    }

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

    // 传当前状态

    // 定义一个标志位，防止上一张图片还没传完下一张就开始，导致堆积
    let isSnapshotting = false;

    setInterval(async () => {
        let snapshotPromise = Promise.resolve();

        // 如果可以截图，则执行截图操作
        if (ws.readyState == WebSocket.OPEN && !isSnapshotting && page) {
            isSnapshotting = true;
            snapshotPromise = page.screenshot({ encoding: 'base64', type: 'jpeg', quality: 50 })
                .then(base64Data => {
                    ws.send(JSON.stringify({
                        source: 'minecraft',
                        type: 'screenshot',
                        content: base64Data,
                        metadata: { user: 'system' }
                    }));
                })
                .catch(e => console.error('Snapshot error:', e))
                .finally(() => isSnapshotting = false);
        }

        // 发送文字状态信息
        snapshotPromise.then(() => {
            try {
                const state = bot.observe();
                ws.send(JSON.stringify({
                    source: 'minecraft',
                    type: 'observation',
                    content: state,  // JSON 字符串
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
    }, 1000); // 1000ms = 1秒
});

async function getGameScreenshot() {
    if (!page) return null;

    // 截图并获取 Base64 字符串 (多模态模型通常需要 Base64)
    // 格式通常是: "data:image/png;base64,....."
    const screenshotBuffer = await page.screenshot({ encoding: 'base64' });
    return screenshotBuffer;
}

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
    } else if (command.type === 'code_run_request') {
        console.log("Executing code...");

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

        const code = command.payload;
        const programs = bot.primitivesCode;

        async function evaluateCode(code, programs) {
            let outputMessages = []; // 用于收集输出

            // 将 report 注入到 eval 可访问的全局作用域
            global.report = (msg) => {
                if (typeof msg === 'string') {
                    outputMessages.push(msg);
                } else {
                    outputMessages.push(JSON.stringify(msg));
                }
            };

            try {
                // 使用 eval 保持作用域访问
                await eval("(async () => {" + programs + "\n" + code + "})()");
                delete global.report;
                return { success: true, messages: outputMessages };
            } catch (err) {
                delete global.report;
                return { success: false, error: err, messages: outputMessages };
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
                    content: result.messages.join('\n') || result.error.stack
                }));
            } else {
                // 执行成功
                console.log("Code executed successfully!");
                ws.send(JSON.stringify({
                    source: 'minecraft',
                    type: 'code_run_result',
                    content: result.messages.join('\n') || "执行完成，无输出。"
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
                content: e.stack
            }));
        } finally {
            // 清理监听器，防止内存泄漏或逻辑冲突
            bot.removeListener("physicsTick", onTick);
        }
    }
});

// Chat Listener
bot.on('chat', (username, message) => {
    if (username === bot.username) return;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ source: 'minecraft', type: 'chat', content: message, metadata: { user: username } }));
    }
});

bot.on('error', err => console.log('Bot Error:', err));
bot.on('kicked', reason => console.log('Bot Kicked:', reason));