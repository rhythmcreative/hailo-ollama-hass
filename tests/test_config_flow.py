"""Tests for Hailo Ollama config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hailo_ollama.const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_PORT,
    CONF_STREAMING,
    CONF_SYSTEM_PROMPT,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SYSTEM_PROMPT,
    DOMAIN,
)


@pytest.fixture
def mock_setup_entry():
    """Mock setting up a config entry."""
    with patch(
        "custom_components.hailo_ollama.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup


async def test_form_connection_error(hass: HomeAssistant, mock_setup_entry) -> None:
    """Test we handle connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.hailo_ollama.config_flow.HailoOllamaConfigFlow._test_connection",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "192.168.1.100",
                CONF_PORT: 8000,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_no_models(hass: HomeAssistant, mock_setup_entry) -> None:
    """Test we handle no models found."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "custom_components.hailo_ollama.config_flow.HailoOllamaConfigFlow._test_connection",
            return_value="1.0.0",
        ),
        patch(
            "custom_components.hailo_ollama.config_flow.HailoOllamaConfigFlow._fetch_models",
            return_value=[],
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: DEFAULT_HOST,
                CONF_PORT: DEFAULT_PORT,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "no_models"}


async def test_form_success(hass: HomeAssistant, mock_setup_entry) -> None:
    """Test successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with (
        patch(
            "custom_components.hailo_ollama.config_flow.HailoOllamaConfigFlow._test_connection",
            return_value="1.0.0",
        ),
        patch(
            "custom_components.hailo_ollama.config_flow.HailoOllamaConfigFlow._fetch_models",
            return_value=["llama3.2:3b", "deepseek-r1:1.5b"],
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: DEFAULT_HOST,
                CONF_PORT: DEFAULT_PORT,
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pick_model"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MODEL: "llama3.2:3b",
            CONF_SYSTEM_PROMPT: DEFAULT_SYSTEM_PROMPT,
            CONF_STREAMING: True,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hailo (llama3.2:3b)"
    assert result["data"] == {
        CONF_HOST: DEFAULT_HOST,
        CONF_PORT: DEFAULT_PORT,
        CONF_MODEL: "llama3.2:3b",
        CONF_SYSTEM_PROMPT: DEFAULT_SYSTEM_PROMPT,
        CONF_STREAMING: True,
    }
