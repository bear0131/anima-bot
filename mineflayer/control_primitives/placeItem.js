async function placeItem(bot, name, position) {
    // return if name is not string
    if (typeof name !== "string") {
        throw new Error(`name for placeItem must be a string`);
    }

    const itemByName = mcData.itemsByName[name];
    if (!itemByName) {
        throw new Error(`No item named ${name}`);
    }

    // --- 新增判定：检查目标位置是否已经是方块 ---
    const targetBlock = bot.blockAt(position);
    if (targetBlock && targetBlock.name !== "air") {
        report(`无法放置 ${name}：位置 ${position} 已经有方块了，类型是 ${targetBlock.name}`);
        return;
    }
    // ---------------------------------------

    const item = bot.inventory.findInventoryItem(itemByName.id);
    if (!item) {
        report(`No ${name} in inventory`);
        return;
    }
    const item_count = item.count;

    // find a reference block
    const faceVectors = [
        new Vec3(0, 1, 0),
        new Vec3(0, -1, 0),
        new Vec3(1, 0, 0),
        new Vec3(-1, 0, 0),
        new Vec3(0, 0, 1),
        new Vec3(0, 0, -1),
    ];
    let referenceBlock = null;
    let faceVector = null;
    for (const vector of faceVectors) {
        const block = bot.blockAt(position.minus(vector));
        if (block?.name !== "air") {
            referenceBlock = block;
            faceVector = vector;
            break;
        }
    }

    if (!referenceBlock) {
        report(
            `No block to place ${name} on. You cannot place a floating block.`
        );
        return;
    }

    bot.setControlState('sneak', true);

    try {
        await bot.equip(item, "hand");
        await bot.placeBlock(referenceBlock, faceVector);
        report(`Placed ${name}`);
        bot.save(`${name}_placed`);
    } catch (err) {
        const item = bot.inventory.findInventoryItem(itemByName.id);
        if (item?.count === item_count) {
            report(
                `Error placing ${name}: ${err.message}, please find another position to place`
            );
        } else {
            report(`Placed ${name}`);
            bot.save(`${name}_placed`);
        }
    }

    bot.setControlState('sneak', false);
}