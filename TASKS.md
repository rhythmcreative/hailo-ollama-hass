# Future Tasks

## Bug Fixes

- [x] Upon sending any chat request, it fails and this error appears. Check the code and fix it. add tests too
  ```Logger: homeassistant.components.assist_pipeline.pipeline
  Source: components/assist_pipeline/pipeline.py:1298
  integration: Assist pipeline (documentation, issues)
  Unexpected error during intent recognition
  
  Traceback (most recent call last):
    File "/usr/src/homeassistant/homeassistant/components/assist_pipeline/pipeline.py", line 1298, in recognize_intent
      conversation_result = await conversation.async_converse(
                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      ...<9 lines>...
      )
      ^
    File "/usr/src/homeassistant/homeassistant/components/conversation/agent_manager.py", line 129, in async_converse
      result = await method(conversation_input)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    File "/usr/src/homeassistant/homeassistant/components/conversation/entity.py", line 55, in internal_async_process
      return await self.async_process(user_input)
                   ~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^
  TypeError: HailoOllamaConversationEntity.async_process() missing 1 required positional argument: 'chat_log'
  ```

## Features

- [x] Add options flow to allow reconfiguring model, system prompt, and streaming mode after initial setup
- [ ] Expose model parameters (temperature, top_p, max_tokens) as configurable options
- [ ] Add sensor entities for response metrics (tokens/sec, response time, token count)
- [ ] Add support for additional languages beyond English in `supported_languages`
- [ ] Implement connection health check / auto-reconnect logic
- [ ] Add Home Assistant diagnostics support for debugging
- [ ] Add service calls for:
  - Listing available models
  - Switching models at runtime
  - Clearing conversation context

## Code Quality

- [ ] Add integration tests with mocked Hailo-Ollama server
- [ ] More granular error types (connection refused vs timeout vs invalid response)

## Documentation

- [ ] Document required Hailo-Ollama server setup
