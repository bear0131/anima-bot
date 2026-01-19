
async function findAndChopTreesForLogs(bot) {
    bot.chat('开始寻找树木以获取原木');

    // 检查是否已有足够的原木
    const currentLogs = bot.inventory.items().filter(item => item.name.includes('_log')).reduce((count, item) => count + item.count, 0);
    const logsNeeded = 3 - currentLogs;

    if (logsNeeded <= 0) {
        bot.chat('已经有足够的原木了');
        return;
    }

    bot.chat(`还需要 ${logsNeeded} 个原木`);

    // 随机选择一个方向进行探索，因为树木通常在地面上
    const directions = [
        new Vec3(1, 0, 1),
        new Vec3(-1, 0, 1),
        new Vec3(1, 0, -1),
        new Vec3(-1, 0, -1)
    ];

    let logsCollected = currentLogs;

    while (logsCollected < 3) {
        // 寻找树木
        const treeBlock = await exploreUntil(bot, directions[Math.floor(Math.random() * directions.length)], 60, () => {
            const trees = bot.findBlocks({
                matching: (block) => {
                    return block.name.includes('_log'); // 匹配所有类型的原木
                },
                maxDistance: 32,
                count: 1
            });
            return trees.length > 0 ? bot.blockAt(trees[0]) : null;
        });

        if (!treeBlock) {
            bot.chat('在规定时间内未找到树木');
            return;
        }

        bot.chat(`发现树木在 ${treeBlock.position.x}, ${treeBlock.position.y}, ${treeBlock.position.z}`);

        // 砍伐树木
        try {
            await bot.collectBlock.collect(treeBlock, { ignoreNoPath: true });

            // 检查是否成功收集到原木
            const newLogsCount = bot.inventory.items().filter(item => item.name.includes('_log')).reduce((count, item) => count + item.count, 0);

            if (newLogsCount > logsCollected) {
                logsCollected = newLogsCount;
                bot.chat(`已收集 ${logsCollected}/3 个原木`);
            }
        } catch (err) {
            bot.chat(`砍树时 出错: ${err.message}`);
        }
    }

    bot.chat('已完成收集3个原木的任务');
}