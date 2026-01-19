// 确保能访问全局变量
console.log('[DEBUG] Global mcData available?', typeof mcData !== 'undefined');
console.log('[DEBUG] mcData.blocksByName available?', mcData && typeof mcData.blocksByName !== 'undefined');

// 调试版本的 exploreUntil
async function exploreUntilDebug(bot, direction, maxTime = 60, callback) {
    if (typeof maxTime !== "number") {
        throw new Error("maxTime must be a number");
    }
    if (typeof callback !== "function") {
        throw new Error("callback must be a function");
    }
    const test = callback();
    if (test) {
        bot.chat("Explore success.");
        return Promise.resolve(test);
    }
    if (direction.x === 0 && direction.y === 0 && direction.z === 0) {
        throw new Error("direction cannot be 0, 0, 0");
    }
    if (
        !(
            (direction.x === 0 || direction.x === 1 || direction.x === -1) &&
            (direction.y === 0 || direction.y === 1 || direction.y === -1) &&
            (direction.z === 0 || direction.z === 1 || direction.z === -1)
        )
    ) {
        throw new Error(
            "direction must be a Vec3 only with value of -1, 0 or 1"
        );
    }
    maxTime = Math.min(maxTime, 1200);

    console.log(`[DEBUG exploreUntil] Starting exploration, direction=${direction}, maxTime=${maxTime}s`);

    return new Promise((resolve, reject) => {
        const dx = direction.x;
        const dy = direction.y;
        const dz = direction.z;

        let explorationInterval;
        let maxTimeTimeout;
        let checkCount = 0;

        const cleanUp = () => {
            clearInterval(explorationInterval);
            clearTimeout(maxTimeTimeout);
            bot.pathfinder.setGoal(null);
        };

        const explore = () => {
            checkCount++;
            const x =
                bot.entity.position.x +
                Math.floor(Math.random() * 20 + 10) * dx;
            const y =
                bot.entity.position.y +
                Math.floor(Math.random() * 20 + 10) * dy;
            const z =
                bot.entity.position.z +
                Math.floor(Math.random() * 20 + 10) * dz;
            let goal = new GoalNear(x, y, z);
            if (dy === 0) {
                goal = new GoalNearXZ(x, z);
            }
            bot.pathfinder.setGoal(goal);

            console.log(`[DEBUG exploreUntil] Check #${checkCount}: Bot at (${Math.floor(bot.entity.position.x)}, ${Math.floor(bot.entity.position.y)}, ${Math.floor(bot.entity.position.z)}), Goal: (${x}, ${y}, ${z})`);

            try {
                const result = callback();
                if (result) {
                    console.log(`[DEBUG exploreUntil] Found target at check #${checkCount}!`);
                    cleanUp();
                    bot.chat("Explore success.");
                    resolve(result);
                } else {
                    console.log(`[DEBUG exploreUntil] Check #${checkCount}: No target found`);
                }
            } catch (err) {
                console.log(`[DEBUG exploreUntil] Error during check:`, err.message);
                cleanUp();
                reject(err);
            }
        };

        explorationInterval = setInterval(explore, 2000);

        maxTimeTimeout = setTimeout(() => {
            console.log(`[DEBUG exploreUntil] Max time (${maxTime}s) reached after ${checkCount} checks`);
            cleanUp();
            bot.chat("Max exploration time reached");
            resolve(null);
        }, maxTime * 1000);
    });
}

async function mineOneLog(bot) {
    // Four cardinal directions
    const directions = [
        new Vec3(1, 0, 0),
        new Vec3(-1, 0, 0),
        new Vec3(0, 0, 1),
        new Vec3(0, 0, -1)
    ];

    // 收集所有木头方块的 ID
    const logBlockIds = [];
    for (const blockName in mcData.blocksByName) {
        if (blockName.endsWith('_log')) {
            const id = mcData.blocksByName[blockName].id;
            logBlockIds.push(id);
        }
    }
    console.log(`[DEBUG] Log block IDs: ${logBlockIds.join(', ')}`);
    console.log(`[DEBUG] Total log block IDs found: ${logBlockIds.length}`);

    // 验证：尝试直接查找 oak_log
    if (mcData.blocksByName.oak_log) {
        console.log(`[DEBUG] oak_log ID: ${mcData.blocksByName.oak_log.id}`);
    }

    for (let i = 0; i < directions.length; i++) {
        const dir = directions[i];
        bot.chat(`Exploring direction ${dir} to find a tree...`);
        const logBlock = await exploreUntilDebug(bot, dir, 60, () => {
            // 先尝试用 oak_log 的 ID 直接查找
            let logs = [];
            if (mcData.blocksByName.oak_log) {
                logs = bot.findBlocks({
                    matching: mcData.blocksByName.oak_log.id,
                    maxDistance: 32,
                    count: 1024
                });
            }

            // 调试输出：显示 findBlocks 的结果
            const pos = bot.entity.position;
            console.log(`[DEBUG findBlocks] Bot at (${Math.floor(pos.x)}, ${Math.floor(pos.y)}, ${Math.floor(pos.z)}), found ${logs.length} oak_log blocks`);

            if (logs.length > 0) {
                console.log(`[DEBUG findBlocks] Log blocks:`, logs.slice(0, 5).map(l => {
                    const block = bot.blockAt(l);
                    return {
                        name: block.name,
                        pos: block.position,
                        distance: Math.floor(l.distanceTo(pos))
                    };
                }));
            }
            // 返回第一个方块对象（不是 Vec3 位置）
            return logs.length > 0 ? bot.blockAt(logs[0]) : null;
        });
        if (logBlock) {
            bot.chat(`Found a ${logBlock.name} at ${logBlock.position}.`);
            await mineBlock(bot, logBlock.name, 1);
            bot.chat("Successfully mined 1 log.");
            return;
        }
        bot.chat("No log found in this direction.");
    }
    bot.chat("Failed to find a log after exploring all directions.");
}

await mineOneLog(bot);