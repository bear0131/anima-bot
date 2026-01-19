// 简单测试: 聊天和查看周围环境

bot.chat("Hello! I'm alive!");

// 等待一会儿
await bot.waitForTicks(20);

// 获取当前位置
const pos = bot.entity.position;
bot.chat(`我在位置: ${Math.floor(pos.x)}, ${Math.floor(pos.y)}, ${Math.floor(pos.z)}`);

// 查看周围的方块
const nearbyBlocks = bot.findBlocks({
    matching: () => true,
    maxDistance: 10,
    count: 20
});

bot.chat(`周围有 ${nearbyBlocks.length} 个方块`);

// 查看背包
const inventory = bot.inventory.items();
bot.chat(`背包里有 ${inventory.length} 种物品`);

if (inventory.length > 0) {
    bot.chat(`第一个物品: ${inventory[0].name} x${inventory[0].count}`);
}

bot.chat("测试完成!");
