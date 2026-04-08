/**
 * 带有高度变化检测的“暴力”搭高
 */
async function scaffold(bot, name) {
    await bot.waitForTicks(3);
    // 1. 检查数据和物品库
    const itemByName = mcData.itemsByName[name];
    if (!itemByName) return;
    
    const item = bot.inventory.findInventoryItem(itemByName.id);
    if (!item) {
        report(`没有 ${name} 可以使用了。`);
        return;
    }

    // 记录起始位置（用于最后判定是否成功）
    const startPos = bot.entity.position.clone();

    // 2. 准备：装备并看向脚底
    try {
        await bot.equip(item, 'hand');
        // 强制看向正下方
        await bot.look(bot.entity.yaw, -Math.PI / 2, true);
    } catch (err) {
        report(`装备物品失败: ${err.message}`);
        return;
    }

    // 3. 【动作阶段】：起跳 + 高频右键
    bot.setControlState('jump', true);
    
    // 使用间隔更短的定时器尝试放置
    const rightClickTimer = setInterval(() => {
        const currentPos = bot.entity.position.floored();
        // 尝试在脚下的方块上放置
        const referenceBlock = bot.blockAt(currentPos.offset(0, -1, 0));
        if (referenceBlock && referenceBlock.name !== 'air') {
            // activateBlock 模拟右键点击
            bot.activateBlock(referenceBlock, new Vec3(0, 1, 0)).catch(() => {});
        }
    }, 50);

    // 4. 【等待阶段】：给物理引擎和网络延迟留出时间
    // 350ms 足够完成一次完整的起跳和方块更新
    await new Promise(resolve => setTimeout(resolve, 400));

    // 5. 【结束阶段】：停止动作
    clearInterval(rightClickTimer);
    bot.setControlState('jump', false);
    
    // 等待一帧让服务器同步位置
    await bot.waitForTicks(1);

    // 6. 【判定阶段】：检查 Y 坐标是否有实质提升
    const endPos = bot.entity.position;
    // 如果 Y 轴提升小于 0.5（通常一个方块是 1.0），说明没跳上去或被挡住了
    if (endPos.y - startPos.y < 0.5) {
        report(`搭高可能失败了：高度未改变。请检查头顶是否有遮挡或物品是否用尽。`);
    } else {
        report(`成功搭高！当前高度: ${endPos.y.toFixed(1)}`);
    }
}