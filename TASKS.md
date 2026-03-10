# Future Tasks

## Bug Fixes

- [x] Fix type hint in `config_flow.py:92` - `async_step_user` returns `TypedDict` instead of `ConfigFlowResult`

## Features

- [ ] Add translations for Greek, German, Italian, Portuguese, Spanish, French, Brazilian Portuguese
- [ ] Allow user to choose in configuration if they want the thinking process to be returned or not
- [ ] Add options flow to allow reconfiguring model, system prompt, and streaming mode after initial setup
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

- [x] Add unit tests for config flow and conversation entity
- [ ] Add integration tests with mocked Hailo-Ollama server
- [ ] More granular error types (connection refused vs timeout vs invalid response)

## Documentation

- [x] Add README.md with installation instructions and screenshots
- [ ] Document required Hailo-Ollama server setup
- [ ] Add HACS manifest for easy installation via HACS
