const mcData = require('minecraft-data')(bot.version);

// 定义所需材料数量
const requiredCobblestone = 3;
const requiredSticks = 2;

// 检查背包中是否有足够的材料
const hasEnoughCobblestone = bot.inventory.count(mcData.itemsByName.cobblestone.id) >= requiredCobblestone;
const hasEnoughSticks = bot.inventory.count(mcData.itemsByName.stick.id) >= requiredSticks;

if (!hasEnoughCobblestone || !hasEnoughSticks) {
    report("Not enough materials to craft a stone pickaxe.");
} else {
    // Check if there's already a crafting table nearby (within 5 blocks)
    let nearbyCraftingTable = bot.findBlock({
        matching: mcData.blocksByName.crafting_table.id,
        maxDistance: 5
    });

    if (!nearbyCraftingTable) {
        // Ensure we have a crafting table in inventory
        const hasCraftingTable = bot.inventory.count(mcData.itemsByName.crafting_table.id) > 0;
        if (!hasCraftingTable) {
            // Try to craft one from planks
            const planksCount = bot.inventory.count(mcData.itemsByName.oak_planks.id);
            if (planksCount >= 4) {
                await craftItem(bot, "crafting_table", 1);
                report("Crafted a crafting table.");
            } else {
                // Need to get logs and make planks
                if (bot.inventory.count(mcData.itemsByName.oak_log.id) === 0) {
                    await mineBlock(bot, "oak_log", 1);
                    report("Mined an oak log.");
                }
                await craftItem(bot, "oak_planks", 4);
                report("Crafted 4 oak planks.");
                await craftItem(bot, "crafting_table", 1);
                report("Crafted a crafting table.");
            }
        }

        // Place the crafting table
        const placePos = bot.entity.position.offset(1, 0, 0);
        await placeItem(bot, "crafting_table", placePos);
        report("Placed a crafting table.");

        // Re-check to ensure it's now nearby
        nearbyCraftingTable = bot.findBlock({
            matching: mcData.blocksByName.crafting_table.id,
            maxDistance: 5
        });
        if (!nearbyCraftingTable) {
            report("Failed to place or detect crafting table. Aborting.");
            return;
        }
    }

    // Now craft the stone pickaxe using the nearby crafting table
    await craftItem(bot, "stone_pickaxe", 1);
    report("Successfully crafted a stone pickaxe.");
}