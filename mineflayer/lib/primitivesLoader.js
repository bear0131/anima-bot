const fs = require('fs');
const path = require('path');

/**
 * Load control primitives from the control_primitives directory
 * These are the full-featured versions with error handling
 */
function loadControlPrimitives() {
    const primitivesDir = path.join(__dirname, '../control_primitives');
    const files = fs.readdirSync(primitivesDir)
        .filter(f => f.endsWith('.js') && f !== '.prettierrc.json');

    let primitives = '';

    for (const file of files) {
        const content = fs.readFileSync(path.join(primitivesDir, file), 'utf8');
        primitives += `// ${file}\n${content}\n\n`;
    }

    return primitives;
}

/**
 * Load control primitives context (simplified versions for LLM)
 * This is optional - for future use when integrating with Python prompts
 */
function loadControlPrimitivesContext() {
    const contextDir = path.join(__dirname, '../control_primitives_context');
    const files = fs.readdirSync(contextDir)
        .filter(f => f.endsWith('.js') && f !== '.prettierrc.json');

    let primitives = '';

    for (const file of files) {
        const content = fs.readFileSync(path.join(contextDir, file), 'utf8');
        primitives += `// ${file}\n${content}\n\n`;
    }

    return primitives;
}

module.exports = {
    loadControlPrimitives,
    loadControlPrimitivesContext,
};