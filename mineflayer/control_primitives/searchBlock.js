async function searchBlock(bot, name, maxDistance = 32) {
    // 1. 验证输入名称
    if (typeof name !== "string") {
        report("Error: name for searchBlock must be a string");
        return;
    }

    // 2. 根据铁律：必须通过 mcData 获取数字 ID
    const blockData = mcData.blocksByName[name];
    if (!blockData) {
        report(`Error: No block named ${name} in mcData`);
        return;
    }

    // 3. 执行搜索 (限制 maxDistance 为 32)
    const distance = Math.min(maxDistance, 32);
    const block = bot.findBlock({
        matching: blockData.id,
        maxDistance: distance
    });

    // 4. 汇报逻辑
    if (block) {
        const pos = block.position;
        // 汇报坐标，方便大脑记录或下一步操作
        report(`Found ${name} at x:${pos.x}, y:${pos.y}, z:${pos.z}`);
        
        // 为了方便后续线性代码引用，可以将结果临时挂载在 bot 对象上
        bot.tempTargetPos = pos; 
        bot.save(`${name}_found`);
    } else {
        report(`Failed to find ${name} within ${distance} blocks.`);
        // 如果找不到，这里可以抛出错误或保持沉默，取决于你希望脚本是否继续
    }
}