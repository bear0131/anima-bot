require('dotenv').config();

const mineflayer = require('mineflayer');
const WebSocket = require('ws');

if (!process.env.MINECRAFT_PORT) {
    throw new Error('MINECRAFT_PORT is required in .env');
}

// --- 1. 复用：插件依赖 ---
const { pathfinder, Movements, goals } = require("mineflayer-pathfinder");
const { plugin: tool } = require("mineflayer-tool");
const { plugin: collectBlock } = require("mineflayer-collectblock");
const { plugin: pvp } = require("mineflayer-pvp");
const { Vec3 } = require("vec3");

// --- 2. 复用：观察层依赖 (确保你拷贝了 lib 文件夹) ---
const obs = require("./lib/observation/base");
const OnChat = require("./lib/observation/onChat");
const OnError = require("./lib/observation/onError");
const { Voxels, BlockRecords } = require("./lib/observation/voxels");
const Status = require("./lib/observation/status");
const Inventory = require("./lib/observation/inventory");
const Chests = require("./lib/observation/chests");

// 初始化 Bot
const bot = mineflayer.createBot({
    host: process.env.MINECRAFT_HOST || 'localhost',
    port: parseInt(process.env.MINECRAFT_PORT, 10),
    username: process.env.BOT_USERNAME || 'mybot'
});

// 初始化 WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/minecraft');

ws.on('open', () => {
    console.log('Connected to Python Brain!');
});

// --- 3. 复用：插件加载与初始化 ---
bot.once('spawn', () => {
    console.log('Bot Spawned, loading plugins...');

    // 加载肌肉
    bot.loadPlugin(pathfinder);
    bot.loadPlugin(tool);
    bot.loadPlugin(collectBlock);
    bot.loadPlugin(pvp);

    // 初始化寻路参数
    const mcData = require("minecraft-data")(bot.version);
    const movements = new Movements(bot, mcData);
    bot.pathfinder.setMovements(movements);

    // 注入感官
    obs.inject(bot, [OnChat, OnError, Voxels, Status, Inventory, Chests, BlockRecords]);

    // 基础设置
    bot.waitTicks = 20;
    bot.chat("/gamerule keepInventory true");
});

// 处理指令
ws.on('message', async (data) => {
    const command = JSON.parse(data);

    if (command.type === 'chat') {
        bot.chat(command.payload);
    }
    else if (command.type === 'run_code') {
        console.log("Executing code...");
        try {
            const AsyncFunction = Object.getPrototypeOf(async function () { }).constructor;

            // 注入常用变量 Vec3, goals，这样 LLM 生成的代码更简洁
            const func = new AsyncFunction('bot', 'require', 'Vec3', 'goals', command.payload);
            await func(bot, require, Vec3, goals);

            // 执行完毕，发送成功回执 + 当前状态观察
            // 注意：bot.observe() 是由 obs.inject 注入的方法
            const state = bot.observe ? bot.observe() : {};
            ws.send(JSON.stringify({
                source: 'minecraft',
                type: 'execution_done',
                status: 'success',
                state: state
            }));

        } catch (e) {
            console.error(e);
            bot.chat(`Error: ${e.message}`);
            ws.send(JSON.stringify({
                source: 'minecraft',
                type: 'execution_done',
                status: 'error',
                error: e.message
            }));
        }
    }
});

// 监听聊天转发给 Python (保持你写的，没问题)
bot.on('chat', (username, message) => {
    if (username === bot.username) return;
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            source: 'minecraft',
            type: 'chat',
            content: message,
            user: username
        }));
    }
});

// 监听错误
bot.on('error', (err) => console.log(err));
bot.on('kicked', (reason) => console.log("Kicked:", reason));