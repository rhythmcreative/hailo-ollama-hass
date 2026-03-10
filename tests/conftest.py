"""Fixtures for Hailo Ollama tests."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


@pytest.fixture
def mock_api_version():
    """Mock successful /api/version response."""
    with patch(
        "aiohttp.ClientSession.get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"version": "1.0.0"})
        mock_get.return_value.__aenter__.return_value = mock_response
        yield mock_get


@pytest.fixture
def mock_api_tags():
    """Mock successful /api/tags response."""
    return {
        "models": [
            {"name": "llama3.2:3b"},
            {"name": "deepseek-r1:1.5b"},
        ]
    }


@pytest.fixture
def mock_chat_response():
    """Mock successful /api/chat response."""
    return {
        "model": "llama3.2:3b",
        "message": {
            "role": "assistant",
            "content": "Hello! How can I help you today?",
        },
        "done": True,
    }


@pytest.fixture
def mock_streaming_chunks():
    """Mock streaming /api/chat response chunks."""
    return [
        b'{"model":"llama3.2:3b","message":{"role":"assistant","content":"Hello"},"done":false}\n',
        b'{"model":"llama3.2:3b","message":{"role":"assistant","content":"!"},"done":false}\n',
        b'{"model":"llama3.2:3b","message":{"role":"assistant","content":" How can I help?"},"done":true}\n',
    ]
