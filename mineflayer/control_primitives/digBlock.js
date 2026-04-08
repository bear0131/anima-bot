async function digBlock(bot, position) {
    if (!position || typeof position.x !== 'number') {
        report("Error: position for digBlock must be a Vec3");
        return;
    }

    const block = bot.blockAt(position);
    const blockName = block?.name;

    if (!block || block.name === "air" || block.name === "cave_air" || block.name === "void_air") {
        report(`No block found at ${position}. It's already air.`);
        return;
    }

    if (!bot.canDigBlock(block)) {
        const distance = bot.entity.position.distanceTo(block.position);
        report(`Cannot dig ${blockName} at ${position}: distance is ${distance.toFixed(2)} (too far or blocked).`);
        return;
    }

    try {
        // 1. 选择工具
        const tool = bot.pathfinder ? bot.pathfinder.bestHarvestTool(block) : null;
        const canHarvest = block.canHarvest(tool ? tool.type : null);

        if (tool) {
            await bot.equip(tool, "hand");
        }

        // 2. 获取当前实际使用的工具名称
        // 获取主手持有的物品
        const heldItem = bot.heldItem;
        const toolUsed = heldItem ? heldItem.name : "bare hands";

        await bot.lookAt(block.position.offset(0.5, 0.5, 0.5));

        report(`Starting to dig ${blockName} at ${position} using ${toolUsed}`);
        await bot.dig(block);

        await bot.waitForTicks(1);
        const finalBlock = bot.blockAt(position);

        if (finalBlock && finalBlock.name === "air") {
            if (canHarvest) {
                // 成功采集，报告使用的工具
                report(`Successfully collected ${blockName} using ${toolUsed}.`);
            } else {
                // 仅破坏，报告使用的工具
                report(`Destroyed ${blockName} with ${toolUsed}, but it was not collected (inefficient tool).`);
            }
            
            if (typeof bot.save === 'function') {
                bot.save(`${blockName}_dug`);
            }
        } else {
            report(`Digging finished but ${blockName} is still there (might be a ghost block).`);
        }

    } catch (err) {
        report(`Error digging ${blockName}: ${err.message}`);
    }
}