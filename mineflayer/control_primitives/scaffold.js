/**
 * 让机器人向上跳跃并同时在脚下放置一个方块，实现“搭高高”。
 * @param {import('mineflayer').Bot} bot - The bot instance.
 * @param {string} name - 要放置的方块的名称，例如 'dirt' 或 'cobblestone'。
 */
async function scaffold(bot, name) {
    // 1. 检查数据和物品库
    const itemByName = mcData.itemsByName[name];
    if (!itemByName) {
        throw new Error(`[scaffold] No item named ${name}`);
    }

    const item = bot.inventory.findInventoryItem(itemByName.id);
    if (!item) {
        bot.chat(`I don't have any ${name} to scaffold with.`);
        return;
    }

    // 3. 装备手持物品
    await bot.equip(item, 'hand');

    // 4. 获取用于挂载新方块的“参考方块” (即机器人正脚底垫着的那个方块)
    const pos = bot.entity.position.floored();
    const referenceBlock = bot.blockAt(pos.offset(0, -1, 0));
    
    if (!referenceBlock || referenceBlock.name === 'air') {
        throw new Error("No block below to place against.");
    }
    
    const faceVector = new Vec3(0, 1, 0); // (0, 1, 0) 代表在参考方块的“顶面”进行放置

    // 5. 核心动作开始：起跳！
    bot.setControlState('jump', true);
    
    // 6. 关键点：等待 4 个物理刻 (大约 200 毫秒)。
    // 此时机器人恰好到达跳跃轨迹的顶点，脚下刚好腾出 > 1.0 的净空。
    await bot.waitForTicks(4);
    bot.setControlState('jump', false); // 松开跳跃键

    // 7. 在最高空执行精准放置
    try {
        // placeBlock 会自动瞬间往下看并且发送最精确的数据包
        await bot.placeBlock(referenceBlock, faceVector);
    } catch (err) {
        throw new Error(`Failed to place block: ${err.message}`);
    }
}