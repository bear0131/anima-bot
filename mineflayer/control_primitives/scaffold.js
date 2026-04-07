/**
 * 判定机器人头顶是否被方块挡住
 * 考虑到机器人 0.6x0.6 的横截面，检查四个角对应的头顶位置
 */
function isHeadBlocked(bot) {
    const pos = bot.entity.position;
    // 机器人身高约 1.8，头顶起跳空间在 Y + 2 的位置
    const headY = Math.floor(pos.y + 2);
    
    // 碰撞箱半径为 0.3 (0.6 / 2)
    const padding = 0.3;
    const checkPoints = [
        new Vec3(pos.x + padding, headY, pos.z + padding),
        new Vec3(pos.x + padding, headY, pos.z - padding),
        new Vec3(pos.x - padding, headY, pos.z + padding),
        new Vec3(pos.x - padding, headY, pos.z - padding)
    ];

    for (const point of checkPoints) {
        const block = bot.blockAt(point.floored());
        // 如果方块存在，且不是空气，且具有物理碰撞体积
        if (block && block.name !== 'air' && block.boundingBox !== 'empty') {
            return true; // 只要有一个点被挡住，就无法起跳
        }
    }
    return false;
}

/**
 * 带有头顶检测的“暴力”搭高
 */
async function scaffold(bot, name) {
    // 1. 检查数据和物品库
    const itemByName = mcData.itemsByName[name];
    if (!itemByName) return;
    const item = bot.inventory.findInventoryItem(itemByName.id);
    if (!item) {
        report(`没有 ${name} 可以使用了。`);
        return;
    }

    // 2. 头顶安全检查
    if (isHeadBlocked(bot)) {
        report("头顶被挡住了，无法搭高！注意头顶周围四个方块都会挡住");
        return; 
    }

    // 3. 准备：装备并看向脚底
    await bot.equip(item, 'hand');
    await bot.look(bot.entity.yaw, -Math.PI / 2, true);

    // 4. 【按下阶段】：起跳 + 高频右键
    bot.setControlState('jump', true);
    
    const rightClickTimer = setInterval(() => {
        const pos = bot.entity.position.floored();
        const referenceBlock = bot.blockAt(pos.offset(0, -1, 0));
        if (referenceBlock && referenceBlock.name !== 'air') {
            bot.activateBlock(referenceBlock, new Vec3(0, 1, 0)).catch(() => {});
        }
    }, 54);

    // 5. 【等待阶段】
    await new Promise(resolve => setTimeout(resolve, 350));

    // 6. 【松开阶段】
    clearInterval(rightClickTimer);
    bot.setControlState('jump', false);
    
    await bot.waitForTicks(1);
}