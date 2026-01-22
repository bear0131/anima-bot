const mcData = require('minecraft-data')(bot.version);

// Check if we already have a crafting table in inventory
const craftingTableCount = bot.inventory.count(mcData.itemsByName.crafting_table.id);
if (craftingTableCount > 0) {
    report('Already have a crafting table in inventory');
} else {
    // Check if we have enough oak_planks to craft one (need 4)
    const planksCount = bot.inventory.count(mcData.itemsByName.oak_planks.id);
    if (planksCount >= 4) {
        await craftItem(bot, 'crafting_table', 1);
        report('Crafted a crafting table from oak planks');
    } else {
        // Need to get oak logs first
        const logsCount = bot.inventory.count(mcData.itemsByName.oak_log.id);
        if (logsCount === 0) {
            // Mine an oak log
            await mineBlock(bot, 'oak_log', 1);
            report('Mined an oak log');
        }
        // Convert log to planks (1 log -> 4 planks via crafting)
        await craftItem(bot, 'oak_planks', 4);
        report('Crafted 4 oak planks from log');
        // Now craft the crafting table
        await craftItem(bot, 'crafting_table', 1);
        report('Crafted a crafting table');
    }
}