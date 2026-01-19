/**
 * 测试代码格式
 *
 * 这个文件展示了 anima-bot 期望的代码格式
 * LLM 应该生成类似这样的代码
 */

// ✅ 正确格式 - 直接写可执行逻辑
const correctCodeExample = `
const block = bot.findBlock({
  matching: mcData.blocksByName.oak_log.id,
  maxDistance: 32
});

if (block) {
  await bot.dig(block);
  bot.chat('Mined oak log!');
}
`;

// ❌ 错误格式 - 不要包含函数声明
const wrongCodeExample = `
async function mineWood(bot) {
  const block = bot.findBlock({
    matching: mcData.blocksByName.oak_log.id,
    maxDistance: 32
  });

  if (block) {
    await bot.dig(block);
    bot.chat('Mined oak log!');
  }
}

await mineWood(bot);
`;

// 模拟执行环境
function simulateExecution(code, programs) {
  // 这就是 anima-bot/index.js 中的执行方式
  const wrappedCode = `(async () => { ${programs} ${code} })()`;

  console.log('=== Wrapped Code ===');
  console.log(wrappedCode);
  console.log('====================');

  return wrappedCode;
}

// 测试
console.log('正确格式的代码:');
console.log(simulateExecution(correctCodeExample, '// programs here\n'));

console.log('\n\n');

console.log('错误格式的代码 (会失败):');
console.log(simulateExecution(wrongCodeExample, '// programs here\n'));
