async function digBlock(bot, position) {
    // 1. 验证位置参数是否合法
    if (!position || typeof position.x !== 'number') {
        report("Error: position for digBlock must be a Vec3");
        return;
    }

    // 2. 获取目标位置的方块实例
    const block = bot.blockAt(position);

    // 3. 检查方块是否可挖掘 (如果已经是空气或不可见则退出)
    if (!block || block.name === "air" || block.name === "cave_air" || block.name === "void_air") {
        report(`No block found at ${position}. It's already air.`);
        return;
    }

    // 4. 原地挖掘核心限制：检查 bot 是否够得着
    // bot.canDigBlock 会检查距离（通常是 4.5 格）以及是否有视线阻挡
    if (!bot.canDigBlock(block)) {
        const distance = bot.entity.position.distanceTo(block.position);
        report(`Cannot dig ${block.name} at ${position}: distance is ${distance.toFixed(2)} (too far or blocked).`);
        return;
    }

    try {
        // 5. 工具准备逻辑 (模仿 placeItem 的物品检查)
        // 自动查找背包中最适合挖掘该方块的工具
        const tool = bot.pathfinder ? bot.pathfinder.bestHarvestTool(block) : null; 
        // 注意：如果完全禁用 pathfinder 插件，这里可以简化为寻找背包里的 pickaxe/axe/shovel
        
        if (tool) {
            await bot.equip(tool, "hand");
        }

        // 6. 视角锁定
        // 挖掘前必须看向方块中心，否则服务端可能会判定挖掘无效
        await bot.lookAt(block.position.offset(0.5, 0.5, 0.5));

        // 7. 执行挖掘
        report(`Starting to dig ${block.name} at ${position}`);
        await bot.dig(block);

        // 8. 成功汇报与状态保存
        report(`Successfully dug ${block.name}`);
        // 模仿你提供的 bot.save 逻辑
        if (typeof bot.save === 'function') {
            bot.save(`${block.name}_dug`);
        }
    } catch (err) {
        // 9. 异常处理与汇报
        report(`Error digging ${block.name}: ${err.message}`);
    }
}