"""Conversation agent for Hailo Ollama."""

from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from typing import Any

import aiohttp

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import intent, llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_HOST,
    CONF_LLM_HASS_API,
    CONF_MODEL,
    CONF_PORT,
    CONF_SHOW_THINKING,
    CONF_STREAMING,
    CONF_SYSTEM_PROMPT,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DEFAULT_LLM_HASS_API,
    DEFAULT_SHOW_THINKING,
    DEFAULT_STREAMING,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    DEFAULT_TOP_P,
    DOMAIN,
    SIGNAL_AVAILABILITY_CHANGED,
    SIGNAL_METRICS_UPDATED,
)

_LOGGER = logging.getLogger(__name__)


def _process_thinking(response_text: str, show_thinking: bool) -> str:
    """Strip or format <think>...</think> reasoning blocks.

    Handles both well-formed <think>...</think> and responses where the
    opening <think> tag is absent (some models omit it in streaming).
    When show_thinking is True the thinking content is wrapped in <i>
    tags so the UI can present it in italic style.
    """
    if "</think>" not in response_text:
        return response_text.strip()

    # Split on the first </think>; everything before is thinking content.
    think_part, _, answer_part = response_text.partition("</think>")

    # Strip the optional leading <think> tag.
    thinking = think_part.removeprefix("<think>").strip()
    answer = answer_part.strip()

    if show_thinking and thinking:
        return f"<i>{thinking}</i>\n\n{answer}"
    return answer


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the conversation agent."""
    async_add_entities([HailoOllamaConversationEntity(entry)])


class HailoOllamaClientMixin:
    """Mixin that provides HTTP client methods for communicating with Hailo-Ollama.

    Subclasses must expose:
      - self._base_url: str
      - self._model: str
      - self._host: str
      - self._port: int
      - self.hass: HomeAssistant
    """

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        stream: bool,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict:
        """Build the minimal /api/chat payload for Oatpp compatibility."""
        payload = {
            "model": str(self._model),
            "messages": messages,
            "stream": bool(stream),
            "options": {
                "temperature": float(self._temperature),
                "top_p": float(self._top_p),
                "repeat_penalty": 1.3,
                "num_predict": 2048,
            }
        }
        if tools:
            payload["tools"] = tools
        return payload

    async def _call_non_streaming(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Call /api/chat with stream:false — single JSON response."""
        url = f"{self._base_url}/api/chat"
        payload = self._build_payload(messages, stream=False, tools=tools)

        _LOGGER.debug(
            "POST %s (non-streaming, %d messages, model=%s, %d tools)",
            url,
            len(messages),
            self._model,
            len(tools) if tools else 0,
        )

        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(
            total=DEFAULT_TIMEOUT, sock_read=DEFAULT_TIMEOUT
        )

        try:
            async with session.post(
                url, json=payload, timeout=timeout
            ) as resp:
                _LOGGER.debug("Response: status=%s", resp.status)

                if resp.status != 200:
                    body = await resp.text()
                    _LOGGER.error("Hailo Ollama error (HTTP %s): %s", resp.status, body)
                    raise HailoError(f"HTTP {resp.status} from Hailo Ollama", details=body)

                data = await resp.json()

        except aiohttp.ClientPayloadError as err:
            _LOGGER.warning(
                "stream:false payload error (%s), retrying with streaming",
                err,
            )
            return await self._call_streaming(messages, tools=tools)

        except aiohttp.ClientConnectorError as err:
            raise HailoError(
                f"Cannot connect to {self._host}:{self._port}"
            ) from err

        except TimeoutError as err:
            raise HailoError(f"Timed out after {DEFAULT_TIMEOUT}s connecting to {self._host}") from err

        if "message" not in data:
            _LOGGER.error("Malformed response from Hailo: %s", json.dumps(data))
            raise HailoError("Malformed response: 'message' key missing", details=data)

        return data

    async def _call_streaming(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Call /api/chat with stream:true — collect ndjson chunks."""
        url = f"{self._base_url}/api/chat"
        payload = self._build_payload(messages, stream=True, tools=tools)

        _LOGGER.debug(
            "POST %s (streaming, %d messages, model=%s, %d tools)",
            url,
            len(messages),
            self._model,
            len(tools) if tools else 0,
        )

        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(
            total=DEFAULT_TIMEOUT, sock_read=DEFAULT_TIMEOUT
        )

        chunks: list[dict] = []
        buffer = b""

        try:
            async with session.post(
                url, json=payload, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    _LOGGER.error("Hailo Ollama streaming error (HTTP %s): %s", resp.status, body)
                    raise HailoError(f"HTTP {resp.status} from Hailo Ollama (streaming)", details=body)

                try:
                    async for data in resp.content.iter_any():
                        buffer += data
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                chunks.append(json.loads(line))
                            except json.JSONDecodeError:
                                _LOGGER.warning(
                                    "Bad chunk: %s", line[:100]
                                )

                    # Flush remaining buffer
                    if buffer.strip():
                        try:
                            chunks.append(json.loads(buffer.strip()))
                        except json.JSONDecodeError:
                            pass

                except aiohttp.ClientPayloadError:
                    _LOGGER.debug(
                        "ClientPayloadError (expected), got %d chunks",
                        len(chunks),
                    )

        except aiohttp.ClientConnectorError as err:
            raise HailoError(
                f"Cannot connect to {self._host}:{self._port}"
            ) from err

        except TimeoutError as err:
            raise HailoError(f"Timed out after {DEFAULT_TIMEOUT}s connecting to {self._host}") from err

        _LOGGER.debug("Stream: %d chunks collected", len(chunks))

        if not chunks:
            raise HailoError("Streaming returned 0 chunks from Hailo Ollama")

        # Combine content from chunks
        final_message = {"role": "assistant", "content": ""}
        for chunk in chunks:
            if chunk.get("error"):
                _LOGGER.error("Error chunk from Hailo: %s", chunk["error"])
                raise HailoError(f"Error from Hailo: {chunk['error']}", details=chunk)
            if "message" in chunk:
                msg = chunk["message"]
                if "content" in msg:
                    final_message["content"] += msg["content"]
                if "tool_calls" in msg:
                    if "tool_calls" not in final_message:
                        final_message["tool_calls"] = []
                    # In Ollama streaming, tool_calls might be incrementally sent or replaced.
                    # Usually they are in the last chunk or sent fully.
                    final_message["tool_calls"] = msg["tool_calls"]

        return {"message": final_message}



class HailoOllamaConversationEntity(
    conversation.ConversationEntity, HailoOllamaClientMixin
):
    """Hailo Ollama conversation agent."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize."""
        self._entry = entry
        # Host and port are only set during initial config, never in options
        self._host: str = entry.data[CONF_HOST]
        self._port: int = entry.data[CONF_PORT]
        # Remaining settings may be overridden via the options flow
        opts = entry.options or {}
        self._model: str = opts.get(CONF_MODEL) or entry.data[CONF_MODEL]
        self._system_prompt: str = opts.get(CONF_SYSTEM_PROMPT) or entry.data.get(
            CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT
        )
        self._llm_hass_api: str = opts.get(CONF_LLM_HASS_API) or entry.data.get(
            CONF_LLM_HASS_API, DEFAULT_LLM_HASS_API
        )
        self._streaming: bool = opts.get(
            CONF_STREAMING, entry.data.get(CONF_STREAMING, DEFAULT_STREAMING)
        )
        self._show_thinking: bool = opts.get(
            CONF_SHOW_THINKING, entry.data.get(CONF_SHOW_THINKING, DEFAULT_SHOW_THINKING)
        )
        self._temperature: float = opts.get(
            CONF_TEMPERATURE, entry.data.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE)
        )
        self._top_p: float = opts.get(
            CONF_TOP_P, entry.data.get(CONF_TOP_P, DEFAULT_TOP_P)
        )
        self._attr_unique_id = entry.entry_id
        self._base_url = f"http://{self._host}:{self._port}"
        self._conversations: dict[str, list[dict[str, Any]]] = {}

    async def async_added_to_hass(self) -> None:
        """Subscribe to availability changes."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_AVAILABILITY_CHANGED.format(self._entry.entry_id),
                self._handle_availability,
            )
        )

    @callback
    def _handle_availability(self, available: bool) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True when the Hailo-Ollama server is reachable."""
        return (
            self.hass.data.get(DOMAIN, {})
            .get(self._entry.entry_id, {})
            .get("available", True)
        )

    @property
    def supported_languages(self) -> str:
        """Return supported languages."""
        return conversation.MATCH_ALL

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"Hailo Ollama ({self._model})",
            "manufacturer": "Hailo",
            "model": self._model,
        }

    def _build_user_message(
        self, text: str, attachments: list | None
    ) -> dict[str, Any]:
        """Build the user message dict, encoding image attachments when applicable."""
        if not attachments:
            return {"role": "user", "content": text}

        images: list[str] = []
        for attachment in attachments:
            raw = getattr(attachment, "content", None)
            if raw is None and isinstance(attachment, (bytes, bytearray)):
                raw = attachment
            if isinstance(raw, (bytes, bytearray)):
                images.append(base64.b64encode(raw).decode("ascii"))
            else:
                _LOGGER.warning(
                    "Skipping attachment with unreadable content: %s",
                    type(attachment),
                )

        if images:
            return {"role": "user", "content": text, "images": images}
        return {"role": "user", "content": text}

    async def _fetch_fact_context(self, text: str) -> str | None:
        """Fetch real facts from the internet to ground the model."""
        # Simple keywords to trigger knowledge lookup
        trigger_words = ["quien", "quién", "qué", "que es", "historia", "cuándo", "donde", "napoleon", "roma", "borbon"]
        if not any(word in text.lower() for word in trigger_words):
            return None

        _LOGGER.info("Fetching real-world facts to prevent hallucinations for: %s", text)
        search_url = f"https://api.duckduckgo.com/?q={text}&format=json&no_html=1&skip_disambig=1"
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(search_url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get("AbstractText")
                    if not result and data.get("RelatedTopics"):
                        result = data["RelatedTopics"][0].get("Text")
                    return result
        except Exception as err:
            _LOGGER.error("Failed to fetch facts: %s", err)
        return None

    async def async_process(
        self,
        user_input: conversation.ConversationInput,
    ) -> conversation.ConversationResult:
        """Process a conversation turn."""
        t0 = time.monotonic()
        user_text = user_input.text
        _LOGGER.debug("User: %s", user_text)

        # 1. FETCH REAL FACTS (RAG Lite)
        fact_context = await self._fetch_fact_context(user_text)
        
        conversation_id = user_input.conversation_id or str(uuid.uuid4())
        history = self._conversations.get(conversation_id, [])

        attachments = getattr(user_input, "attachments", None)
        user_message = self._build_user_message(user_text, attachments)

        # 2. INJECT KNOWLEDGE INTO SYSTEM PROMPT
        current_system_prompt = self._system_prompt
        if fact_context:
            current_system_prompt += f"\n\nCONTEXTO REAL (USA ESTO PARA RESPONDER): {fact_context}"
            _LOGGER.info("Injected facts into prompt: %s", fact_context[:100])

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": current_system_prompt},
        ]
        messages.extend(history)
        messages.append(user_message)

        # Get tools if an LLM API is configured
        api_instance: llm.APIInstance | None = None
        tools: list[dict[str, Any]] | None = None
        if self._llm_hass_api != DEFAULT_LLM_HASS_API:
            try:
                # Create the required LLMContext for the new HA API
                llm_context = llm.LLMContext(
                    platform=DOMAIN,
                    context=user_input.context,
                    user_prompt=user_input.text,
                    device_id=user_input.device_id,
                )
                # Pass the llm_context as required by HA 2025/2026
                api_instance = await llm.async_get_api(
                    self.hass,
                    self._llm_hass_api,
                    llm_context=llm_context,
                )
                tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        },
                    }
                    for tool in api_instance.tools
                ]
            except Exception as err:
                _LOGGER.exception("Failed to get LLM API")

        # Call Hailo with configured mode, handling tool calls in a loop
        response_text = ""
        success = False
        try:
            for iteration in range(10):  # Limit tool call iterations
                if self._streaming:
                    data = await self._call_streaming(messages, tools=tools)
                else:
                    data = await self._call_non_streaming(messages, tools=tools)
                
                # If it's a raw string (from old _call_* implementation), wrap it
                if isinstance(data, str):
                    data = {"message": {"role": "assistant", "content": data}}

                assistant_msg = data.get("message", {})
                messages.append(assistant_msg)
                
                tool_calls = assistant_msg.get("tool_calls")
                if not tool_calls or not api_instance:
                    response_text = assistant_msg.get("content", "")
                    success = True
                    break

                _LOGGER.debug("Processing %d tool calls", len(tool_calls))
                for tool_call in tool_calls:
                    function = tool_call.get("function", {})
                    name = function.get("name")
                    args = function.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            _LOGGER.warning("Failed to parse tool arguments: %s", args)
                            args = {}

                    _LOGGER.info("Calling tool %s with %s", name, args)
                    try:
                        # Standard Home Assistant tool
                        # Pass context to tool call if possible
                        tool_input = llm.ToolInput(
                            tool_name=name, 
                            tool_args=args,
                            context=user_input.context,
                            agent_id=user_input.agent_id,
                            device_id=user_input.device_id,
                        )
                        tool_result = await api_instance.async_call_tool(tool_input)
                        # Convert to string to avoid Oatpp mapping errors (HTTP 500)
                        tool_result_str = str(tool_result)
                        
                        messages.append({
                            "role": "tool",
                            "name": name,
                            "content": tool_result_str,
                        })
                    except Exception as err:
                        _LOGGER.exception("Tool execution error for '%s'", name)
                        messages.append({
                            "role": "tool",
                            "name": name,
                            "content": f"Error: {err}",
                        })
                
                # Continue the loop to get the assistant's response to the tool results
            else:
                _LOGGER.warning("Reached maximum tool call iterations")
                response_text = "I reached the maximum number of tool calls and had to stop."
                success = True

        except HailoError as err:
            _LOGGER.error("Hailo error: %s (Details: %s)", err, err.details)
            response_text = f"Sorry, I encountered an error: {err}"
            if err.details:
                response_text += f"\n\nDetails: {err.details}"
        except Exception as err:
            _LOGGER.exception("Unexpected error in async_process")
            response_text = f"Sorry, an unexpected error occurred: {err}"

        elapsed = time.monotonic() - t0

        clean_text = _process_thinking(response_text, self._show_thinking)
        if success:
            async_dispatcher_send(
                self.hass,
                SIGNAL_METRICS_UPDATED.format(self._entry.entry_id),
                {"response_time": round(elapsed, 2), "response_chars": len(clean_text)},
            )
        if clean_text != response_text.strip():
            _LOGGER.debug(
                "Processed <think> tags: %d → %d chars",
                len(response_text),
                len(clean_text),
            )

        _LOGGER.info(
            "Hailo responded in %.1fs (%d chars): %.100s",
            elapsed,
            len(clean_text),
            clean_text,
        )

        # Store plain text in history for simplicity, or we could store the full message sequence
        updated_history = list(history)
        updated_history.append({"role": "user", "content": user_text})
        updated_history.append({"role": "assistant", "content": clean_text})
        self._conversations[conversation_id] = updated_history

        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(clean_text)

        return conversation.ConversationResult(
            response=response,
            conversation_id=conversation_id,
        )



class HailoError(Exception):
    """Error from Hailo Ollama."""

    def __init__(self, message: str, details: Any = None) -> None:
        """Initialize."""
        super().__init__(message)
        self.details = details
