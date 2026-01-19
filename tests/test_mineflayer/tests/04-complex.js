// 复杂测试：探索+挖矿+合成
await exploreUntil(bot, 'oak_log', 32, 32);
await mineBlock(bot, 'oak_log', 3);
await craftItem(bot, 'oak_planks', 4);
bot.chat('Complex test completed!');
