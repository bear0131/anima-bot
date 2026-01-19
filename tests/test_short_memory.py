"""
Unit tests for ShortTermMemory module
"""

import pytest
from collections import deque
from datetime import datetime
from agent.short_memory import ShortTermMemory
from agent.schema import Event, AgentState, MCState


@pytest.fixture
def empty_agent_state():
    """Fixture providing an empty AgentState"""
    return AgentState()


@pytest.fixture
def populated_agent_state():
    """Fixture providing an AgentState with populated MCState"""
    mc_state = MCState(
        biome="plains",
        time_of_day="day",
        health=18.5,
        hunger=15.0,
        position={"x": 100.5, "y": 64.0, "z": -200.3},
        equipment=["diamond_sword", "iron_chestplate"],
        entities={"zombie": 5.2, "cow": 3.1, "chicken": 2.8},
        inventory={"oak_log": 64, "stone": 32, "cobblestone": 16},
        inventory_used=3,
        nearby_blocks=["grass_block", "dirt", "stone", "oak_log", "cobblestone"]
    )
    return AgentState(mc_state=mc_state)


@pytest.fixture
def sample_events():
    """Fixture providing sample events for testing"""
    return [
        Event(type="user_chat", content="Hello bot", source="user"),
        Event(type="bot_chat", content="Hello! How can I help?", source="bot"),
        Event(type="action_start", content="Craft a pickaxe", source="system"),
        Event(type="action_end", content="Successfully crafted", source="system"),
        Event(type="error", content="Failed to find resource", source="system"),
        Event(type="system_log", content="Inventory full", source="system"),
    ]


class TestShortTermMemoryInitialization:
    """Test suite for ShortTermMemory initialization"""

    def test_default_initialization(self, empty_agent_state):
        """Test initialization with default parameters"""
        memory = ShortTermMemory(empty_agent_state)
        assert isinstance(memory.events, deque)
        assert len(memory.events) == 0
        assert memory.events.maxlen == 20
        assert memory.state == empty_agent_state
        assert memory.last_screenshot is None

    def test_custom_max_history(self, empty_agent_state):
        """Test initialization with custom max_history"""
        memory = ShortTermMemory(empty_agent_state, max_history=50)
        assert memory.events.maxlen == 50

    def test_initialization_with_populated_state(self, populated_agent_state):
        """Test initialization with populated AgentState"""
        memory = ShortTermMemory(populated_agent_state)
        assert memory.state == populated_agent_state
        assert memory.state.mc_state is not None


class TestAddEvent:
    """Test suite for add_event method"""

    def test_add_single_event(self, empty_agent_state):
        """Test adding a single event"""
        memory = ShortTermMemory(empty_agent_state)
        event = Event(type="user_chat", content="Test message", source="user")

        memory.add_event(event)

        assert len(memory.events) == 1
        assert memory.events[0] == event

    def test_add_multiple_events(self, empty_agent_state, sample_events):
        """Test adding multiple events"""
        memory = ShortTermMemory(empty_agent_state)

        for event in sample_events:
            memory.add_event(event)

        assert len(memory.events) == len(sample_events)

    def test_event_queue_maxlen_enforcement(self, empty_agent_state):
        """Test that deque respects maxlen when adding events"""
        memory = ShortTermMemory(empty_agent_state, max_history=3)

        for i in range(5):
            event = Event(type="system_log", content=f"Message {i}", source="system")
            memory.add_event(event)

        # Should only keep the last 3 events
        assert len(memory.events) == 3
        assert memory.events[0].content == "Message 2"
        assert memory.events[-1].content == "Message 4"


class TestGetLastEvent:
    """Test suite for get_last_event method"""

    def test_get_last_event_from_empty_memory(self, empty_agent_state):
        """Test getting last event from empty memory"""
        memory = ShortTermMemory(empty_agent_state)

        assert memory.get_last_event() is None

    def test_get_last_event_single_item(self, empty_agent_state):
        """Test getting last event with one item"""
        memory = ShortTermMemory(empty_agent_state)
        event = Event(type="user_chat", content="Test", source="user")
        memory.add_event(event)

        last_event = memory.get_last_event()

        assert last_event is not None
        assert last_event.content == "Test"

    def test_get_last_event_multiple_items(self, empty_agent_state, sample_events):
        """Test getting last event with multiple items"""
        memory = ShortTermMemory(empty_agent_state)

        for event in sample_events:
            memory.add_event(event)

        last_event = memory.get_last_event()

        assert last_event is not None
        assert last_event.type == "system_log"
        assert last_event.content == "Inventory full"


class TestRenderStateForPrompt:
    """Test suite for render_state_for_prompt method"""

    def test_render_with_no_mc_state(self, empty_agent_state):
        """Test rendering when mc_state is None"""
        memory = ShortTermMemory(empty_agent_state)

        result = memory.render_state_for_prompt()

        assert result == "当前状态: 未知\n"

    def test_render_with_full_mc_state(self, populated_agent_state):
        """Test rendering with fully populated MCState"""
        memory = ShortTermMemory(populated_agent_state)

        result = memory.render_state_for_prompt()

        assert "### 当前游戏状态" in result
        assert "位置: x=100.5, y=64.0, z=-200.3" in result
        assert "生物群系: plains" in result
        assert "时间: day" in result
        assert "生命值: 18.5/20" in result
        assert "饥饿值: 15.0/20" in result
        assert "装备: diamond_sword, iron_chestplate" in result
        assert "周围方块:" in result
        assert "附近实体:" in result
        assert "物品栏 (3/36):" in result
        assert "oak_logx64" in result
        assert "stonex32" in result

    def test_render_with_minimal_mc_state(self):
        """Test rendering with minimal MCState data"""
        mc_state = MCState(biome="forest")
        agent_state = AgentState(mc_state=mc_state)
        memory = ShortTermMemory(agent_state)

        result = memory.render_state_for_prompt()

        assert "### 当前游戏状态" in result
        assert "生物群系: forest" in result
        assert "位置: 未知" in result
        assert "时间: 未知" in result
        assert "生命值: 0.0/20" in result
        assert "饥饿值: 0.0/20" in result

    def test_render_entities_sorted_by_distance(self, populated_agent_state):
        """Test that entities are sorted by distance in output"""
        memory = ShortTermMemory(populated_agent_state)

        result = memory.render_state_for_prompt()

        # Entities should appear sorted: chicken (2.8), cow (3.1), zombie (5.2)
        lines = result.split('\n')
        entities_line = next(l for l in lines if "附近实体:" in l)

        # Check that closer entities appear first
        assert entities_line.index("chicken") < entities_line.index("cow")
        assert entities_line.index("cow") < entities_line.index("zombie")

    def test_render_nearby_blocks_limited(self):
        """Test that nearby blocks are limited to 10 items"""
        blocks = [f"block_{i}" for i in range(20)]
        mc_state = MCState(nearby_blocks=blocks)
        agent_state = AgentState(mc_state=mc_state)
        memory = ShortTermMemory(agent_state)

        result = memory.render_state_for_prompt()

        # Should only show first 10 blocks
        assert "block_0" in result
        assert "block_9" in result
        assert "block_10" not in result

    def test_render_without_equipment(self):
        """Test rendering when equipment is None"""
        mc_state = MCState(health=10.0)
        agent_state = AgentState(mc_state=mc_state)
        memory = ShortTermMemory(agent_state)

        result = memory.render_state_for_prompt()

        # Should not include equipment line
        assert "装备:" not in result


class TestRenderLLMContext:
    """Test suite for render_llm_context method"""

    def test_render_empty_memory(self, empty_agent_state):
        """Test rendering context with no events"""
        memory = ShortTermMemory(empty_agent_state)

        result = memory.render_llm_context(include_image=False)

        assert isinstance(result, list)
        assert len(result) == 1  # Only system message with state
        assert result[0]["role"] == "system"
        assert "当前状态: 未知" in result[0]["content"]

    def test_render_with_various_event_types(self, empty_agent_state, sample_events):
        """Test rendering context with different event types"""
        memory = ShortTermMemory(empty_agent_state)

        for event in sample_events:
            memory.add_event(event)

        result = memory.render_llm_context(include_image=False)

        # Check user_chat event
        assert any(m["role"] == "user" and "Hello bot" in m["content"] for m in result)

        # Check bot_chat event
        assert any(m["role"] == "assistant" and "Hello! How can I help?" in m["content"] for m in result)

        # Check action_start event
        assert any(m["role"] == "system" and "开始执行任务: Craft a pickaxe" in m["content"] for m in result)

        # Check action_end event
        assert any(m["role"] == "system" and "任务结束. 结果: Successfully crafted" in m["content"] for m in result)

        # Check error event
        assert any(m["role"] == "system" and "Failed to find resource" in m["content"] and "[Error]" in m["content"] for m in result)

    def test_render_with_screenshot(self, populated_agent_state):
        """Test rendering context with screenshot included"""
        populated_agent_state.last_screenshot = "base64encodedimagedata"
        memory = ShortTermMemory(populated_agent_state)

        result = memory.render_llm_context(include_image=True)

        # Find the image message
        image_message = next(m for m in result if isinstance(m["content"], list))

        assert image_message["role"] == "user"
        assert image_message["content"][0]["type"] == "text"
        assert "这是你现在看到的景象" in image_message["content"][0]["text"]
        assert image_message["content"][1]["type"] == "image_url"
        assert "data:image/jpeg;base64,base64encodedimagedata" in image_message["content"][1]["image_url"]["url"]
        assert image_message["content"][1]["image_url"]["detail"] == "low"

    def test_render_without_screenshot(self, populated_agent_state):
        """Test rendering context without screenshot"""
        memory = ShortTermMemory(populated_agent_state)

        result = memory.render_llm_context(include_image=False)

        # No message should have image_url content
        for message in result:
            if isinstance(message["content"], list):
                assert not any(c["type"] == "image_url" for c in message["content"])

    def test_render_with_screenshot_disabled(self, populated_agent_state):
        """Test that include_image=False prevents screenshot inclusion"""
        populated_agent_state.last_screenshot = "base64encodedimagedata"
        memory = ShortTermMemory(populated_agent_state)

        result = memory.render_llm_context(include_image=False)

        # Should not include image even though screenshot is available
        for message in result:
            if isinstance(message["content"], list):
                assert not any(c["type"] == "image_url" for c in message["content"])

    def test_event_source_in_user_chat(self, empty_agent_state):
        """Test that event source is included in user chat messages"""
        memory = ShortTermMemory(empty_agent_state)
        event = Event(type="user_chat", content="Attack the zombie", source="player1")
        memory.add_event(event)

        result = memory.render_llm_context(include_image=False)

        user_message = next(m for m in result if m["role"] == "user")
        assert "[player1]:" in user_message["content"]

    def test_system_message_order(self, empty_agent_state, sample_events):
        """Test that system state message comes after events"""
        memory = ShortTermMemory(empty_agent_state)

        for event in sample_events:
            memory.add_event(event)

        result = memory.render_llm_context(include_image=False)

        # Last message should be the system state message (when no image)
        assert result[-1]["role"] == "system"
        assert "当前游戏状态" in result[-1]["content"] or "当前状态: 未知" in result[-1]["content"]

    def test_unknown_event_type_handling(self, empty_agent_state):
        """Test that unknown event types are ignored"""
        memory = ShortTermMemory(empty_agent_state)

        # Add events including unknown type
        memory.add_event(Event(type="user_chat", content="Hello", source="user"))
        memory.add_event(Event(type="unknown_type", content="Unknown", source="system"))
        memory.add_event(Event(type="bot_chat", content="Hi", source="bot"))

        result = memory.render_llm_context(include_image=False)

        # Should only render user_chat and bot_chat, not unknown_type
        assert len([m for m in result if m["role"] in ["user", "assistant"]]) == 2


class TestEdgeCases:
    """Test suite for edge cases and special scenarios"""

    def test_none_position_handling(self):
        """Test handling of None position in MCState"""
        mc_state = MCState(position=None)
        agent_state = AgentState(mc_state=mc_state)
        memory = ShortTermMemory(agent_state)

        result = memory.render_state_for_prompt()

        assert "位置: 未知" in result

    def test_empty_inventory(self):
        """Test rendering with empty inventory"""
        mc_state = MCState(inventory={}, inventory_used=0)
        agent_state = AgentState(mc_state=mc_state)
        memory = ShortTermMemory(agent_state)

        result = memory.render_state_for_prompt()

        # Empty inventory dict is falsy, so it won't be displayed
        assert "物品栏" not in result

    def test_no_nearby_entities(self):
        """Test rendering when no entities nearby"""
        mc_state = MCState(entities={})
        agent_state = AgentState(mc_state=mc_state)
        memory = ShortTermMemory(agent_state)

        result = memory.render_state_for_prompt()

        # Empty entities dict is falsy, so it won't be displayed
        assert "附近实体" not in result

    def test_large_inventory(self):
        """Test rendering with many inventory items"""
        inventory = {f"item_{i}": i for i in range(40)}
        mc_state = MCState(inventory=inventory, inventory_used=36)
        agent_state = AgentState(mc_state=mc_state)
        memory = ShortTermMemory(agent_state)

        result = memory.render_state_for_prompt()

        assert "物品栏 (36/36):" in result
        assert "item_0" in result
        assert "item_39" in result

    def test_rapid_event_addition(self, empty_agent_state):
        """Test adding many events quickly"""
        memory = ShortTermMemory(empty_agent_state, max_history=100)

        events = [Event(type="system_log", content=f"Log {i}", source="system") for i in range(1000)]
        for event in events:
            memory.add_event(event)

        # Should only keep last 100 due to maxlen
        assert len(memory.events) == 100

    def test_event_timestamp_preservation(self, empty_agent_state):
        """Test that event timestamps are preserved"""
        memory = ShortTermMemory(empty_agent_state)

        event1 = Event(type="user_chat", content="First", source="user")
        import time
        time.sleep(0.01)
        event2 = Event(type="user_chat", content="Second", source="user")

        memory.add_event(event1)
        memory.add_event(event2)

        assert memory.events[0].timestamp < memory.events[1].timestamp

    def test_metadata_preservation(self, empty_agent_state):
        """Test that event metadata is preserved"""
        memory = ShortTermMemory(empty_agent_state)

        event = Event(
            type="user_chat",
            content="Test",
            source="user",
            metadata={"priority": "high", "category": "combat"}
        )
        memory.add_event(event)

        assert memory.events[0].metadata == {"priority": "high", "category": "combat"}
