"""Button entities for Hailo Ollama."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SIGNAL_CLEAR_HISTORY

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hailo Ollama button entities."""
    async_add_entities([HailoClearHistoryButton(entry)])

class HailoClearHistoryButton(ButtonEntity):
    """Button to clear the conversation history."""

    _attr_has_entity_name = True
    _attr_translation_key = "clear_history"
    _attr_icon = "mdi:delete-sweep"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_clear_history"

    @property
    def device_info(self) -> dict:
        """Return device info."""
        return {"identifiers": {(DOMAIN, self._entry.entry_id)}}

    async def async_press(self) -> None:
        """Handle the button press."""
        async_dispatcher_send(
            self.hass, 
            SIGNAL_CLEAR_HISTORY.format(self._entry.entry_id)
        )
