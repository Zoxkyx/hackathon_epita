from unittest.mock import patch

from src.agents.planner import plan_sessions


def test_plan_sessions_calls_call_structured_and_returns_sessions():
    fake_result = {"sessions": [{"title": "Intro", "focus": "bases", "goal": "comprendre X"}]}
    with patch("src.agents.planner.call_structured", return_value=fake_result) as mock_call:
        result = plan_sessions("Apprendre X", 1)
    assert result == fake_result["sessions"]
    args, kwargs = mock_call.call_args
    assert "Apprendre X" in args[1]
    assert "1" in args[1]
