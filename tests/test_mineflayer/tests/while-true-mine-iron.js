
// Write your code here. This should be the body of an async function, NOT a complete function declaration.
// Just write the executable logic directly.
// DO NOT include 'async function' declaration.
// DO NOT include function name or parameters.
// Just write the code that would go inside the function body.

const mcData = require('minecraft-data')(bot.version);

while (true) {
    try {
        // Attempt to mine iron ore using the provided utility
        await mineBlock(bot, 'iron_ore', 1);
        report('Mined 1 iron ore');
    } catch (err) {
        // If mineBlock fails (e.g., no iron_ore nearby), explore first
        const directions = [
            { x: 1, z: 0 },
            { x: -1, z: 0 },
            { x: 0, z: 1 },
            { x: 0, z: -1 },
            { x: 1, z: 1 },
            { x: -1, z: -1 },
            { x: 1, z: -1 },
            { x: -1, z: 1 }
        ];
        const randomDir = directions[Math.floor(Math.random() * directions.length)];
        await exploreUntil(bot, randomDir, 32, () => {
            const block = bot.findBlock({
                matching: mcData.blocksByName.iron_ore.id,
                maxDistance: 32
            });
            return !!block;
        });
    }
}