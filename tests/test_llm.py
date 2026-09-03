from unittest.mock import MagicMock, patch

from src.llm import call_structured


class FakeBlock:
    def __init__(self, type, input=None):
        self.type = type
        self.input = input


def test_call_structured_extracts_tool_input():
    fake_response = MagicMock()
    fake_response.content = [FakeBlock("tool_use", input={"a": 1})]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    with patch("src.llm.get_client", return_value=fake_client):
        result = call_structured("system", "user", "my_tool", {"type": "object", "properties": {}})
    assert result == {"a": 1}
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "my_tool"}
    assert call_kwargs["system"] == "system"


def test_call_structured_raises_without_tool_use_block():
    fake_response = MagicMock()
    fake_response.content = [FakeBlock("text", input=None)]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    with patch("src.llm.get_client", return_value=fake_client):
        raised = False
        try:
            call_structured("system", "user", "my_tool", {})
        except ValueError:
            raised = True
        assert raised


def test_call_structured_uses_cache_control_when_cacheable():
    fake_response = MagicMock()
    fake_response.content = [FakeBlock("tool_use", input={})]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    with patch("src.llm.get_client", return_value=fake_client):
        call_structured("system text", "user", "my_tool", {}, cacheable_system=True)
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == [{"type": "text", "text": "system text", "cache_control": {"type": "ephemeral"}}]
