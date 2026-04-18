"""Select entities for Hailo Ollama."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_HOST, CONF_PORT, CONF_MODEL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hailo Ollama select entities."""
    async_add_entities([HailoModelSelect(entry)])

class HailoModelSelect(SelectEntity):
    """Select entity to change the active model."""

    _attr_has_entity_name = True
    _attr_translation_key = "model_select"
    _attr_icon = "mdi:brain"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_model_select"
        self._attr_current_option = entry.options.get(CONF_MODEL) or entry.data.get(CONF_MODEL)
        self._attr_options = [self._attr_current_option] if self._attr_current_option else []

    @property
    def device_info(self) -> dict:
        """Return device info."""
        return {"identifiers": {(DOMAIN, self._entry.entry_id)}}

    async def async_update(self) -> None:
        """Fetch available models from the server."""
        host = self._entry.data[CONF_HOST]
        port = self._entry.data[CONF_PORT]
        session = async_get_clientsession(self.hass)
        
        try:
            async with session.get(f"http://{host}:{port}/api/tags", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    if models:
                        self._attr_options = sorted(models)
                        # Ensure current option is still valid
                        current = self._entry.options.get(CONF_MODEL) or self._entry.data.get(CONF_MODEL)
                        if current in self._attr_options:
                            self._attr_current_option = current
                else:
                    _LOGGER.error("Failed to fetch models: %s", resp.status)
        except Exception as err:
            _LOGGER.error("Error updating models list: %s", err)

    async def async_select_option(self, option: str) -> None:
        """Change the active model."""
        _LOGGER.info("Changing Hailo model to: %s", option)
        
        new_options = dict(self._entry.options)
        new_options[CONF_MODEL] = option
        
        # Update config entry options - this will trigger a reload via update_listener
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self._attr_current_option = option
        self.async_write_ha_state()
