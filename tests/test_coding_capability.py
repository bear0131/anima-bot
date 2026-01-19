pytest_plugins = ("pytest_asyncio",)

import pytest
import asyncio
import os
from datetime import datetime
from unittest.mock import Mock, AsyncMock

from agent.capabilities.coding import CodingCapability
from agent.schema import Event, AgentState, MCState
from agent.short_memory import ShortTermMemory


@pytest.fixture
def mock_agent_state():
    """创建一个模拟的 AgentState"""
    state = AgentState(
        status="IDLE",
        mc_state=MCState(
            biome="plains",
            time_of_day="day",
            health=20.0,
            hunger=20.0,
            position={"x": 100.0, "y": 64.0, "z": 200.0},
            equipment=["diamond_sword", "iron_pickaxe"],
            entities={"zombie": 5.2, "cow": 3.1},
            inventory={"oak_log": 10, "stone": 5},
            inventory_used=2,
            nearby_blocks=["grass_block", "dirt", "oak_log"]
        ),
        last_screenshot="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    return state


@pytest.fixture
def mock_short_term_memory(mock_agent_state):
    """创建一个模拟的 ShortTermMemory"""
    memory = ShortTermMemory(agent_state=mock_agent_state, max_history=20)

    # 添加一些测试事件
    memory.add_event(Event(
        type="chat",
        content="Hello bot!",
        source="user",
        metadata={"user": "Player1"}
    ))

    memory.add_event(Event(
        type="chat",
        content="Hi there!",
        source="bot",
        metadata={}
    ))

    return memory


@pytest.fixture
def coding_capability():
    """创建 CodingCapability 实例（使用真实的 OpenAI 客户端）"""
    return CodingCapability()


class TestCodingCapability:
    """测试 CodingCapability 类"""

    def test_initialization(self, coding_capability):
        """测试初始化"""
        assert coding_capability.client is not None
        assert coding_capability.model_name is not None
        assert coding_capability._programs_context is not None
        assert coding_capability._system_template is not None

    @pytest.mark.asyncio
    async def test_can_handle_with_chat_event(self, coding_capability, mock_short_term_memory):
        """测试 can_handle 对 chat 事件的判断"""
        # 添加一个 chat 事件
        mock_short_term_memory.add_event(Event(
            type="chat",
            content="测试消息",
            source="user",
            metadata={"user": "TestUser"}
        ))

        can_process, is_exclusive = await coding_capability.can_handle(mock_short_term_memory)

        assert can_process is True
        assert is_exclusive is False

    @pytest.mark.asyncio
    async def test_can_handle_with_non_chat_event(self, coding_capability, mock_short_term_memory):
        """测试 can_handle 对非 chat 事件的判断"""
        # 添加一个非 chat 事件
        mock_short_term_memory.add_event(Event(
            type="system_log",
            content="系统日志",
            source="system",
            metadata={}
        ))

        can_process, is_exclusive = await coding_capability.can_handle(mock_short_term_memory)

        assert can_process is False
        assert is_exclusive is False

    @pytest.mark.asyncio
    async def test_can_handle_with_empty_memory(self, coding_capability, mock_agent_state):
        """测试 can_handle 对空记忆的处理"""
        empty_memory = ShortTermMemory(agent_state=mock_agent_state, max_history=20)

        can_process, is_exclusive = await coding_capability.can_handle(empty_memory)

        assert can_process is False  # 空记忆，最后一个事件是 None
        assert is_exclusive is False

    @pytest.mark.asyncio
    async def test_get_decision_returns_correct_format(self, coding_capability, mock_short_term_memory):
        """测试 get_decision 返回的格式是否正确（真实 API 调用）"""
        # 注意：这个测试会调用真实的 OpenAI API
        # 确保环境变量 OPENAI_API_KEY 已设置

        # 添加一个明确的代码请求
        mock_short_term_memory.add_event(Event(
            type="chat",
            content="帮我挖一个方块",
            source="user",
            metadata={"user": "Player1"}
        ))

        # 调用 get_decision（这会发送真实的 API 请求）
        decision = await coding_capability.get_decision(mock_short_term_memory)

        # 调试：打印完整返回
        print(f"\n=== 完整 decision ===")
        print(decision)
        print(f"=== content 长度: {len(decision['content'])} ===")
        print(f"=== content 内容 ===")
        print(repr(decision['content']))  # 用 repr 可以看到空格等隐藏字符

        # 验证返回格式
        assert isinstance(decision, dict)
        assert "type" in decision
        assert "content" in decision
        assert "reason" in decision
        assert decision["type"] == "run_code"
        assert isinstance(decision["content"], str)
        assert isinstance(decision["reason"], str)

        # 验证代码不为空
        assert len(decision["content"]) > 0

        print(decision['content'])

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="需要设置 OPENAI_API_KEY 环境变量"
    )
    async def test_get_decision_with_complex_task(self, coding_capability, mock_short_term_memory):
        """测试 get_decision 处理复杂任务（真实 API 调用）"""
        # 添加一个复杂的任务
        mock_short_term_memory.add_event(Event(
            type="chat",
            content="制作一把木镐，然后去挖石头",
            source="user",
            metadata={"user": "Player1"}
        ))

        decision = await coding_capability.get_decision(mock_short_term_memory)

        # 验证返回格式
        assert decision["type"] == "run_code"
        assert len(decision["content"]) > 0
        assert len(decision["reason"]) > 0

        # 验证代码包含有效的 JavaScript 语法特征
        # (这里只是简单检查，实际执行需要 mineflayer 环境)
        assert "bot" in decision["content"].lower() or "mineflayer" in decision["content"].lower()

        print(decision['content'])

    def test_load_control_primitives_with_specific_names(self, coding_capability):
        """测试加载指定的控制原语"""
        primitives = coding_capability._load_control_primitives(["exploreUntil", "mineBlock"])

        assert isinstance(primitives, str)
        assert len(primitives) > 0
        # 验证包含相关函数名
        assert "exploreUntil" in primitives or "mineBlock" in primitives

    def test_load_control_primitives_with_nonexistent_file(self, coding_capability):
        """测试加载不存在的控制原语"""
        primitives = coding_capability._load_control_primitives(["nonexistent_function"])

        # 不存在的文件应该被跳过，返回空字符串或部分内容
        assert isinstance(primitives, str)

    def test_system_template_replacement(self, coding_capability):
        """测试 system prompt 模板的占位符替换"""
        system_content = coding_capability._system_template.replace("{programs}", "test_programs")

        assert "{programs}" not in system_content
        assert "test_programs" in system_content


@pytest.mark.integration
class TestCodingCapabilityIntegration:
    """集成测试 - 需要真实的 API 和环境"""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="需要设置 OPENAI_API_KEY 环境变量"
    )
    async def test_full_coding_workflow(self, coding_capability, mock_short_term_memory):
        """测试完整的编码工作流"""
        # 1. 添加用户请求
        mock_short_term_memory.add_event(Event(
            type="chat",
            content="收集 10 个橡木原木",
            source="user",
            metadata={"user": "Player1"}
        ))

        # 2. 检查是否能处理
        can_process, is_exclusive = await coding_capability.can_handle(mock_short_term_memory)
        assert can_process is True

        # 3. 获取决策
        decision = await coding_capability.get_decision(mock_short_term_memory)
        assert decision["type"] == "run_code"
        assert len(decision["content"]) > 0

        # 4. 验证代码包含预期的函数调用
        # (这里检查是否包含相关的 mineflayer API 调用)
        code = decision["content"].lower()
        assert any(keyword in code for keyword in ["bot", "collect", "mine", "log"])

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="需要设置 OPENAI_API_KEY 环境变量"
    )
    async def test_render_llm_context_includes_screenshot(self, mock_short_term_memory):
        """测试 render_llm_context 是否包含截图信息"""
        messages = mock_short_term_memory.render_llm_context(include_image=True)

        # 验证消息列表不为空
        assert len(messages) > 0

        # 验证包含图片消息
        image_messages = [msg for msg in messages if isinstance(msg.get("content"), list)]
        assert len(image_messages) > 0

        # 验证图片格式
        image_msg = image_messages[0]
        assert image_msg["role"] == "user"
        assert image_msg["content"][0]["type"] == "text"
        assert image_msg["content"][1]["type"] == "image_url"
        assert "data:image/jpeg;base64," in image_msg["content"][1]["image_url"]["url"]
