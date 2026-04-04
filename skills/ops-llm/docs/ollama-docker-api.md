# Ollama Docker-based CLI and HTTP API Reference

**Container**: `scillm-ollama`
**Port**: 11434
**Version**: 0.14.3-rc2

## Docker Exec Pattern

All Ollama CLI commands use the pattern:
```bash
docker exec scillm-ollama ollama <command> [args]
```

## Command Reference

### 1. List Models

**Docker CLI**:
```bash
docker exec scillm-ollama ollama list
```

**HTTP API**:
```bash
curl -s http://localhost:11434/api/tags | jq
```

**Response** (HTTP API):
```json
{
  "models": [
    {
      "name": "llama3.2:1b",
      "modified_at": "2024-01-15T10:30:00Z",
      "size": 1234567890,
      "digest": "sha256:..."
    }
  ]
}
```

### 2. Pull Model

**Docker CLI**:
```bash
docker exec scillm-ollama ollama pull <model-name>
```

**HTTP API**:
```bash
curl -X POST http://localhost:11434/api/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "llama3.2:1b"}'
```

**Response** (HTTP API): Streaming JSON with progress updates

### 3. Remove Model

**Docker CLI**:
```bash
docker exec scillm-ollama ollama rm <model-name>
```

**HTTP API**:
```bash
curl -X DELETE http://localhost:11434/api/delete \
  -H "Content-Type: application/json" \
  -d '{"name": "llama3.2:1b"}'
```

### 4. Show Model Details

**Docker CLI**:
```bash
docker exec scillm-ollama ollama show <model-name>
```

**HTTP API**:
```bash
curl -X POST http://localhost:11434/api/show \
  -H "Content-Type: application/json" \
  -d '{"name": "llama3.2:1b"}'
```

**Response** (HTTP API):
```json
{
  "modelfile": "...",
  "parameters": "...",
  "template": "...",
  "details": {
    "format": "gguf",
    "family": "llama",
    "families": ["llama"],
    "parameter_size": "1B",
    "quantization_level": "Q4_0"
  }
}
```

### 5. List Running Models

**Docker CLI**:
```bash
docker exec scillm-ollama ollama ps
```

**HTTP API**:
```bash
curl -s http://localhost:11434/api/ps | jq
```

**Response** (HTTP API):
```json
{
  "models": [
    {
      "name": "llama3.2:1b",
      "size": 1234567890,
      "expires_at": "2024-01-15T11:00:00Z"
    }
  ]
}
```

### 6. Version Check

**Docker CLI**:
```bash
docker exec scillm-ollama ollama --version
```

**HTTP API**:
```bash
curl -s http://localhost:11434/api/version | jq
```

**Response** (HTTP API):
```json
{
  "version": "0.14.3-rc2"
}
```

## Service Management (Docker-based)

### Container Status

```bash
docker ps --filter "name=scillm-ollama"
```

### Container Logs

```bash
docker logs scillm-ollama --tail 100 --follow
```

### Restart Container

```bash
docker restart scillm-ollama
```

### Stop/Start Container

```bash
docker stop scillm-ollama
docker start scillm-ollama
```

## Performance Monitoring

### GPU Usage (via nvidia-smi)

```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader
```

### Container Stats

```bash
docker stats scillm-ollama --no-stream
```

## Notes

1. **Prefer HTTP API** for programmatic access (faster, more reliable)
2. **Use Docker CLI** for interactive operations or when HTTP API is unavailable
3. **All API endpoints** are at `http://localhost:11434/api/...`
4. **Port mapping**: Container port 11434 → Host port 11434
5. **Image**: `ollama/ollama:0.14.3-rc2`

## Testing

Verify both methods work:
```bash
# CLI method
docker exec scillm-ollama ollama list

# API method
curl -s http://localhost:11434/api/tags | jq '.models[].name'
```

Both should return the same list of models.
