# LLM Chat Service

Modular, production-ready service for interactive chat with Ollama models.

## Features

- ✅ List and select from available Ollama models
- ✅ Interactive chat with conversation history
- ✅ WebSocket support for streaming responses
- ✅ Conversation persistence
- ✅ RESTful API design
- ✅ Fully modular architecture
- ✅ Type-safe with Pydantic models

## Installation

```bash
pip install fastapi uvicorn aiohttp
```

## Usage

### Start the service

```bash
cd "standalone modules/chat_with_llm"
uvicorn chat_api:app --host 0.0.0.0 --port 9001 --reload
```

### API Documentation

Once running, visit:

- Swagger UI: http://localhost:9001/docs
- ReDoc: http://localhost:9001/redoc

## API Endpoints

### Core Endpoints

- `GET /health` - Service health check
- `GET /models` - List available models
- `POST /chat/init` - Initialize chat session
- `POST /chat/message` - Send message (non-streaming)
- `WS /ws/chat` - WebSocket chat (streaming)

### Conversation Management

- `GET /conversations` - List all conversations
- `GET /conversations/{id}` - Get conversation history
- `DELETE /conversations/{id}` - Delete conversation

### Statistics

- `GET /stats` - Get service statistics

## Configuration

Set environment variables:

```bash
export OLLAMA_HOST=localhost
export OLLAMA_PORT=11434
```

## Architecture

```
chat_with_llm/
├── chat_api.py       # FastAPI application
├── chat_client.py    # Ollama API client
├── chat_manager.py   # Conversation management
├── chat_models.py    # Pydantic models
├── chat_config.py    # Configuration
└── README.md         # This file
```

## Example Usage

### Python Client

```python
import httpx

# List models
response = httpx.get("http://localhost:9001/models")
models = response.json()

# Initialize chat
response = httpx.post("http://localhost:9001/chat/init", json={
    "model": "llama3.2"
})
conv_id = response.json()["conversation_id"]

# Send message
response = httpx.post("http://localhost:9001/chat/message", json={
    "conversation_id": conv_id,
    "message": "Hello!"
})
print(response.json()["message"]["content"])
```

### WebSocket Client

```javascript
const ws = new WebSocket("ws://localhost:9001/ws/chat");

// Initialize
ws.send(
  JSON.stringify({
    action: "init",
    model: "llama3.2",
  })
);

// Send message
ws.send(
  JSON.stringify({
    action: "message",
    message: "Hello!",
  })
);

// Receive chunks
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "chunk") {
    process.stdout.write(data.content);
  }
};
```

## License

MIT
