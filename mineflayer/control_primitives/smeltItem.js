async function smeltItem(bot, itemName, fuelName, itemCount, fuelCount) {
    // 1. 参数校验
    if (typeof itemName !== "string" || typeof fuelName !== "string") {
        throw new Error("itemName 和 fuelName 必须是字符串");
    }
    if (typeof itemCount !== "number" || typeof fuelCount !== "number") {
        throw new Error("itemCount 和 fuelCount 必须是数字");
    }
    if (itemCount <= 0) return; // 如果需要烧的数量为 0，直接返回

    // 2. 获取物品 ID
    const mcData = require('minecraft-data')(bot.version);
    const item = mcData.itemsByName[itemName];
    const fuel = mcData.itemsByName[fuelName];

    if (!item) throw new Error(`未找到名为 ${itemName} 的物品`);
    if (!fuel) throw new Error(`未找到名为 ${fuelName} 的物品`);

    // 3. 寻找熔炉并走过去
    const furnaceBlock = bot.findBlock({
        matching: mcData.blocksByName.furnace.id,
        maxDistance: 32,
    });

    if (!furnaceBlock) {
        throw new Error("附近没有找到熔炉 (furnace)");
    }

    // 走向熔炉
    const { GoalLookAtBlock } = require('mineflayer-pathfinder').goals;
    await bot.pathfinder.goto(new GoalLookAtBlock(furnaceBlock.position, bot.world));
    
    // 🔴 核心修复：走到位后必须关闭寻路系统，防止和容器交互时因移动被打断！
    bot.pathfinder.setGoal(null);
    await bot.waitForTicks(10); // 给服务器一点时间同步位置

    // 4. 打开熔炉
    const furnace = await bot.openFurnace(furnaceBlock);

    try {
        // 5. 放入燃料 (如果有指定数量)
        if (fuelCount > 0) {
            // 检查背包里有没有足够的燃料
            const fuelInInv = bot.inventory.items().filter(i => i.name === fuelName).reduce((acc, i) => acc + i.count, 0);
            if (fuelInInv < fuelCount) {
                report(`警告：背包里的 ${fuelName} 数量 (${fuelInInv}) 不足期望投入的数量 (${fuelCount})。`);
            }
            
            // 投入燃料
            await furnace.putFuel(fuel.id, null, fuelCount);
            await bot.waitForTicks(10); // 等待网络同步
        }

        // 6. 放入待烧物品
        const itemInInv = bot.inventory.items().filter(i => i.name === itemName).reduce((acc, i) => acc + i.count, 0);
        if (itemInInv < itemCount) {
            report(`警告：背包里的 ${itemName} 数量 (${itemInInv}) 不足期望烧制数量 (${itemCount})。`);
        }
        
        await furnace.putInput(item.id, null, itemCount);
        await bot.waitForTicks(10);

        // 7. 智能等待烧制完成
        report(`已将 ${itemCount}个 ${itemName} 和 ${fuelCount}个 ${fuelName} 放入熔炉，开始烧制...`);
        
        // 计算最大超时时间 (每个物品原版烧制需要 10 秒即 200 tick，这里多给 30 秒缓冲)
        const maxWaitSeconds = (itemCount * 10) + 30; 
        let elapsedSeconds = 0;

        while (true) {
            const currentInput = furnace.inputItem();
            
            // 如果输入槽空了（全部烧完），退出等待
            if (!currentInput || currentInput.count === 0) {
                break;
            }

            // 检查燃料是否耗尽：如果没有燃料物品了，且燃烧进度(furnace.fuel)降到了0
            if ((!furnace.fuelItem() || furnace.fuelItem().count === 0) && furnace.fuel === 0) {
                report(`熔炉的燃料耗尽了！还有 ${currentInput.count}个 ${itemName} 没烧完。`);
                break;
            }

            // 等待 1 秒钟
            await bot.waitForTicks(20);
            elapsedSeconds++;

            // 超时保护
            if (elapsedSeconds >= maxWaitSeconds) {
                report(`烧制等待超时 (超过 ${maxWaitSeconds} 秒)，强制停止等待。`);
                break;
            }
        }

        // 8. 取出烧好的产物
        const outItem = furnace.outputItem();
        if (outItem && outItem.count > 0) {
            const outCount = outItem.count;
            const outName = outItem.name;
            await furnace.takeOutput(); // 拿取产物
            report(`烧制完成！成功取出了 ${outCount} 个 ${outName}。`);
        } else {
            report(`熔炉输出槽里什么都没有，请检查 ${itemName} 是否真的可以被烧制。`);
        }

    } catch (err) {
        report(`烧制操作中途发生错误: ${err.message}`);
    } finally {
        // 9. 无论成功还是失败，必须关闭熔炉！(否则 Bot 永远卡在 GUI 里)
        furnace.close();
    }
}