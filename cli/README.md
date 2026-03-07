# stark-jarvis

**J.A.R.V.I.S. Terminal Client** — Access your AI assistant from any terminal, anywhere.

## Install

```bash
pip install stark-jarvis
```

## Quick Start

```bash
# Connect to your JARVIS server
jarvis login https://your-jarvis-server.com

# Interactive chat
jarvis

# One-shot query
jarvis "What's the weather in New York?"

# Use a specific model
jarvis --model gemini "Explain quantum computing"
```

## Commands

| Command | Description |
|---------|-------------|
| `jarvis login <url>` | Authenticate with a JARVIS server |
| `jarvis` | Start interactive chat |
| `jarvis "message"` | Send a one-shot query |
| `jarvis --model <provider>` | Use specific provider (claude, gemini, stark_protocol) |
| `jarvis status` | Show connection status |
| `jarvis logout` | Clear stored credentials |
| `jarvis purge` | Remove all config from this machine |

## Interactive Commands

Once in a chat session:

| Command | Description |
|---------|-------------|
| `/model <provider>` | Switch LLM provider |
| `/model` | Show current provider |
| `/new` | Start new conversation |
| `/help` | Show help |
| `exit` | Quit |

## Security

- Credentials are encrypted with a local access code (PBKDF2 + Fernet)
- Nothing is stored in plain text
- `jarvis purge` removes everything from the machine
- Designed for Iron Man 3 scenarios — use any device, clean up when done
