const mcData = require('minecraft-data')(bot.version);

while (true) {
    try {
        await mineBlock(bot, 'oak_log', 1);
        report('Mined 1 oak log');
    } catch (err) {
        // Generate a valid direction vector: each component must be -1, 0, or 1, and not all zero
        const dx = Math.floor(Math.random() * 3) - 1; // -1, 0, 1
        const dz = Math.floor(Math.random() * 3) - 1; // -1, 0, 1
        let direction = { x: dx, y: 0, z: dz };
        if (direction.x === 0 && direction.z === 0) {
            // Ensure at least one horizontal component is non-zero
            direction.x = 1;
        }
        await exploreUntil(bot, direction, 32, () => {
            const block = bot.findBlock({
                matching: mcData.blocksByName.oak_log.id,
                maxDistance: 32
            });
            return !!block;
        });
    }
}