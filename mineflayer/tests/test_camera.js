const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../../.env') });
const mineflayer = require('mineflayer');
const { mineflayer: mineflayerViewer } = require('D:/anima-bot/mineflayer/prismarine-viewer');
const puppeteer = require('puppeteer');

// ============================================================
//  配置与参数解析
// ============================================================

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
const headlessMode = argv.headless !== 'false';
const TARGET_FOV = argv.fov ? parseFloat(argv.fov) : 110.0;

console.log(`[Config] Headless: ${headlessMode}`);
console.log(`[Config] Target FOV: ${TARGET_FOV}`);

// ============================================================
//  初始化 Bot
// ============================================================

const bot = mineflayer.createBot({
    host: process.env.MINECRAFT_HOST || 'localhost',
    port: process.env.MINECRAFT_PORT ? parseInt(process.env.MINECRAFT_PORT) : 25565,
    username: process.env.BOT_USERNAME || 'CameraTestBot',
    version: process.env.MINECRAFT_VERSION || '1.18.2'
});

let browser = null;
let page = null;
let viewerPort = 3008;

bot.once('spawn', async () => {
    console.log('[Bot] Spawned successfully. Bot is in the world!');

    try {
        // 1. 启动 Viewer
        mineflayerViewer(bot, {
            port: viewerPort,
            firstPerson: true,
            viewDistance: 6,
        });
        console.log(`[Viewer] Started on http://localhost:${viewerPort}`);

        // 2. 启动 Puppeteer
        console.log('[Puppeteer] Launching browser...');
        browser = await puppeteer.launch({
            headless: headlessMode,
            // devtools: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        page = await browser.newPage();
        await page.setViewport({ width: 1280, height: 720 });

        // 在 navigation (page.goto) 之前插入
        await page.setRequestInterception(true);

        page.on('request', async (request) => {
            const url = request.url();
            // 拦截我们本地 viewer 服务的所有 js 文件
            if (url.endsWith('.js') && url.includes(`localhost:${viewerPort}`)) {
                try {
                    // 在 Node.js 端用 fetch 把真实代码拉下来
                    const response = await fetch(url);
                    let body = await response.text();

                    // WebGL (Three.js) 这里一般会硬编码 PerspectiveCamera 默认视角为 75。
                    // 无论它被混淆成了什么名字，创建相机的参数逻辑肯定类似于:
                    // new n.PerspectiveCamera(75, window.innerWidth ... )
                    // 我们用正则表达式直接把这个默认值改成你的目标 FOV。
                    body = body.replace(/PerspectiveCamera\(\s*75/g, `PerspectiveCamera(${TARGET_FOV}`);

                    // 将篡改后的代码返回给无头浏览器
                    await request.respond({
                        status: 200,
                        contentType: 'application/javascript',
                        body: body
                    });
                } catch (err) {
                    console.error('拦截替换 JS 失败:', err);
                    request.continue();
                }
            } else {
                // 其他请求（如 html、图片等）正常放行
                request.continue();
            }
        });

        // 然后再执行你的:
        // await page.goto(`http://localhost:${viewerPort}`, { waitUntil: 'domcontentloaded' });

        console.log(`[Puppeteer] Navigating to viewer...`);
        // 等待基础 HTML 框架建立
        await page.goto(`http://localhost:${viewerPort}`, { waitUntil: 'domcontentloaded' });

        // 获取所有的全局变量键名并过滤掉浏览器自带的常见属性
        const globalKeys = await page.evaluate(() => {
            const iframeKeys = Object.keys(window);
            // 粗略过滤掉常见的内置对象
            return iframeKeys.filter(k => !/^(webkit|on|DOM|CSS|HTML|crypto|chrome|speech)/.test(k));
        });
        // console.log('[Debug] 当前 window 上存在的非标准全局变量有:', globalKeys);

        // 取消单纯的等待死停顿，马上开始执行测试逻辑（测试逻辑里面包含了轮询等待）
        await runCameraTests();

    } catch (err) {
        console.error('[Critical] Setup failed:', err);
        cleanupAndExit(1);
    }
});

// ============================================================
//  核心测试逻辑
// ============================================================

async function runCameraTests() {
        /*
    console.log('\n=== 开始相机系统测试 ===\n');

    // --- 测试 1: 修改 FOV (广角) ---
    console.log(`[Test 1] 尝试修改 FOV 至 ${TARGET_FOV}...（等待前端 Viewer 加载）`);

    try {
        // 使用前端轮询，最长等待 10 秒，直到 window.viewer 出现
        const currentFov = await page.evaluate((targetFov) => {
            return new Promise((resolve) => {
                let attempts = 0;
                const checkInterval = setInterval(() => {
                    attempts++;
                    // 定期检查全局对象是否已经挂载完成
                    if (window.viewer && window.viewer.camera) {
                        clearInterval(checkInterval);
                        const oldFov = window.viewer.camera.fov;
                        window.viewer.camera.fov = targetFov;
                        window.viewer.camera.updateProjectionMatrix(); // 必须更新矩阵才生效
                        resolve({ success: true, old: oldFov, new: window.viewer.camera.fov });
                    } else if (attempts > 50) {
                        // 50次 * 200毫秒 = 10秒超时
                        clearInterval(checkInterval);
                        resolve({ success: false, error: '等待 10 秒仍未找到 window.viewer，前端加载过慢或失败。' });
                    }
                }, 200); // 每 200ms 检测一次
            });
        }, TARGET_FOV);

        if (currentFov.success) {
            console.log(`[Success] 前端加载完成，FOV 已成功修改: ${currentFov.old} -> ${currentFov.new}`);
        } else {
            console.warn(`[Warn] 自动修改 FOV 失败: ${currentFov.error}`);
        }

    } catch (e) {
        console.error('[Error] FOV Modification failed:', e);
    }

    // --- 测试 2: 键盘旋转视野 ---
    console.log('\n[Test 2] 启动键盘旋转监听...');
    console.log('请点击弹出的浏览器窗口，然后使用方向键控制视角:');
    console.log('  ↑ : 抬头');
    console.log('  ↓ : 低头');
    console.log('  ← : 左转');
    console.log('  → : 右转');
    console.log('  R : 重置视角');
    console.log('  Q : 退出测试\n');

    await page.exposeFunction('reportRotation', ({ yaw, pitch, reset }) => {
        if (reset) {
            bot.look(0, 0, true);
            console.log('[Action] 视角已重置');
            return;
        }

        const currentYaw = bot.entity.yaw;
        const currentPitch = bot.entity.pitch;

        const newYaw = currentYaw + (yaw * Math.PI / 180);
        const newPitch = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, currentPitch + (pitch * Math.PI / 180)));

        bot.look(newYaw, newPitch, true);
        console.log(`[Action] 旋转视角: 偏航 ${yaw}°, 俯仰 ${pitch}° | 当前 Yaw: ${newYaw.toFixed(2)}, Pitch: ${newPitch.toFixed(2)}`);
    });

    // 浏览器端按键监听
    await page.evaluate(() => {
        document.addEventListener('keydown', (e) => {
            let yawChange = 0;
            let pitchChange = 0;
            let reset = false;

            switch (e.key) {
                // 原本是 -15，根据你的要求翻转正负。
                case 'ArrowUp': pitchChange = 15; break;
                case 'ArrowDown': pitchChange = -15; break;

                case 'ArrowLeft': yawChange = 15; break;
                case 'ArrowRight': yawChange = -15; break;
                case 'r': case 'R': reset = true; break;
                case 'q': case 'Q':
                    window.testQuit = true;
                    return;
            }

            if (reset || yawChange !== 0 || pitchChange !== 0) {
                if (window.reportRotation) {
                    window.reportRotation({ yaw: yawChange, pitch: pitchChange, reset: reset });
                }
            }
        });
    });

    console.log('=== 测试环境就绪，正在运行... ===\n');*/

    const checkInterval = setInterval(async () => {
        console.log('checking');
        //const shouldQuit = await page.evaluate(() => window.testQuit);
        /*
        try {
            const shouldQuit = await page.evaluate(() => window.testQuit);
            if (shouldQuit) {
                clearInterval(checkInterval);
                console.log('[System] 收到退出指令，正在清理...');
                cleanupAndExit(0);
            }
        } catch (err) {
            clearInterval(checkInterval);
            console.log('[System] 浏览器页面已关闭，正在退出...');
            cleanupAndExit(0);
        }
            */
    }, 10000);
}

// ============================================================
//  清理与退出
// ============================================================

async function cleanupAndExit(code) {
    if (browser) {
        await browser.close().catch(() => { });
    }
    if (bot) {
        bot.end();
    }
    process.exit(code);
}

process.on('SIGINT', () => cleanupAndExit(0));
process.on('SIGTERM', () => cleanupAndExit(0));

bot.on('error', (err) => {
    console.error('[Bot Error]', err.message);
    cleanupAndExit(1);
});

bot.on('kicked', (reason) => {
    console.error('[Bot Kicked]', reason);
    cleanupAndExit(1);
});
