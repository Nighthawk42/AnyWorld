"""Unit tests for AnyLLM provider integration and configuration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.schemas import ScenarioTitle
from logic.llm_manager import LLMContextManager
from any_llm.any_llm import AnyLLM
from any_llm.types.completion import (
    ParsedChatCompletion,
    ParsedChoice,
    ParsedChatCompletionMessage,
    CompletionUsage,
)


@pytest.mark.parametrize(
    "provider_setting,expected_provider,expected_api_base",
    [
        ("compatible", "openai", "http://localhost:8033/v1"),
        ("openai", "openai", None),
        ("ollama", "ollama", "http://localhost:8033/v1"),
        ("anthropic", "anthropic", None),
    ],
)
def test_create_client_configures_any_llm_provider(
    provider_setting, expected_provider, expected_api_base
):
    """LLMContextManager._create_client configures AnyLLM with the proper provider and base."""
    with patch.object(AnyLLM, "create") as mock_create:
        mock_instance = MagicMock(spec=AnyLLM)
        mock_instance.client = MagicMock()
        mock_create.return_value = mock_instance

        manager = LLMContextManager()
        with patch("logic.llm_manager.settings") as mock_settings:
            mock_settings.llm.provider = provider_setting
            mock_settings.llm.api_key = "test-key"
            mock_settings.llm.endpoint = "http://localhost:8033/v1"
            mock_settings.llm.request_timeout_seconds = 60.0
            mock_settings.llm.debug_raw_responses = False

            client = manager._create_client()
            assert client is not None

            mock_create.assert_called_once()
            called_provider = mock_create.call_args[0][0]
            assert called_provider == expected_provider
            kwargs = mock_create.call_args[1]
            assert kwargs.get("api_key") == "test-key"
            assert kwargs.get("timeout") == 60.0
            if expected_api_base:
                assert kwargs.get("api_base") == expected_api_base
            else:
                assert "api_base" not in kwargs


def test_attempt_calls_any_llm_acompletion():
    """Provider attempt invokes acompletion and parses structured output when client is AnyLLM."""

    async def run():
        mock_client = MagicMock(spec=AnyLLM)
        parsed_title = ScenarioTitle(title="The Ancient Crypt")
        choice = ParsedChoice(
            message=ParsedChatCompletionMessage(
                role="assistant",
                content='{"title": "The Ancient Crypt"}',
                parsed=parsed_title,
            ),
            finish_reason="stop",
            index=0,
        )
        completion_response = ParsedChatCompletion(
            id="test-id",
            choices=[choice],
            created=123456789,
            model="gpt-4o",
            object="chat.completion",
            usage=CompletionUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        mock_client.acompletion = AsyncMock(return_value=completion_response)

        manager = LLMContextManager(mock_client)
        messages = [{"role": "user", "content": "Generate a title."}]

        result, raw_text = await manager._parse_attempt(
            messages=messages,
            schema=ScenarioTitle,
            kind="title",
            count=10,
            attempt=0,
        )

        assert result.title == "The Ancient Crypt"
        assert raw_text == '{"title": "The Ancient Crypt"}'
        mock_client.acompletion.assert_awaited_once()

    import asyncio

    asyncio.run(run())
