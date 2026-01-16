require('dotenv').config();

const mineflayer = require('mineflayer');
const WebSocket = require('ws');

if (!process.env.MINECRAFT_PORT) {
    throw new Error('MINECRAFT_PORT is required in .env');
}

// 1. 启动 Bot
const bot = mineflayer.createBot({
    host: process.env.MINECRAFT_HOST || 'localhost',
    port: parseInt(process.env.MINECRAFT_PORT, 10),
    username: process.env.BOT_USERNAME || 'mybot'
});

// 2. 连接 Python
const ws = new WebSocket('ws://localhost:8000/ws/minecraft');

ws.on('open', () => {
    console.log('Connected to Python Brain!');
});

// 3. 接收 Python 指令并执行
ws.on('message', async (data) => {
    const command = JSON.parse(data);

    if (command.type === 'chat') {
        bot.chat(command.payload);
    }
    else if (command.type === 'run_code') {
        try {
            // 动态执行 JS
            const AsyncFunction = Object.getPrototypeOf(async function () { }).constructor;
            const func = new AsyncFunction('bot', 'require', command.payload);
            await func(bot, require);
        } catch (e) {
            bot.chat(`Code Error: ${e.message}`);
        }
    }
});

// 4. 监听 MC 事件并发给 Python
bot.on('chat', (username, message) => {
    if (username === bot.username) return;

    const event = {
        source: 'minecraft',
        type: 'chat',
        content: message,
        metadata: { username: username }
    };

    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(event));
    }
});

bot.on('spawn', () => {
    console.log('Bot Spawned in Game');
});