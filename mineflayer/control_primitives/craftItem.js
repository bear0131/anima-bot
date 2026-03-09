async function craftItem(bot, name, craftingTablePos, count = 1) {
    // return if name is not string
    if (typeof name !== "string") {
        throw new Error("name for craftItem must be a string");
    }
    // return if count is not number
    if (typeof count !== "number") {
        throw new Error("count for craftItem must be a number");
    }
    const itemByName = mcData.itemsByName[name];
    if (!itemByName) {
        throw new Error(`No item named ${name}`);
    }
    if (craftingTablePos && bot.entity.position.distanceTo(craftingTablePos) > 4){
        report("Too far away from the crafting table");
        return;
    }
    let craftingTable = null;
    if (craftingTablePos)
        craftingTable = bot.blockAt(craftingTablePos);
    const recipe = bot.recipesFor(itemByName.id, null, 1, craftingTable)[0];
    if (recipe) {
        report(`Crafting ${name} x${count}`);
        try {
            await bot.craft(recipe, count, craftingTable);
            report(`Successfully crafted ${name} x${count}`);
        } catch (err) {
            report(`Failed to craft ${name}: ${err.message}`);
        }
    } else {
        failedCraftFeedback(bot, name, itemByName, craftingTable);
    }
}
