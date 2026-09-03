import os

import anthropic

from src.config import MODEL_NAME

_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def call_structured(system_prompt: str, user_prompt: str, tool_name: str, input_schema: dict,
                     max_tokens: int = 2000, cacheable_system: bool = False) -> dict:
    client = get_client()
    system = system_prompt
    if cacheable_system:
        system = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[{"name": tool_name, "description": f"Retourne {tool_name}", "input_schema": input_schema}],
        tool_choice={"type": "tool", "name": tool_name},
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise ValueError("Aucun bloc tool_use dans la réponse du modèle.")
