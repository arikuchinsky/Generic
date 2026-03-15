# Claude Code Web Wrapper

A web-based interface for Claude Code that runs in your browser. Chat with Claude, upload documents, and use guided skills like **Contract Review & Revise** to review and redline Word documents.

## Quick Start (macOS)

```bash
git clone <repo-url> && cd Generic
./setup.sh
```

That's it. The script will:
1. Install prerequisites (Homebrew, Python 3.10+, Node.js 18+, Claude Code CLI)
2. Create a Python virtual environment and install backend dependencies
3. Install frontend dependencies
4. Start both servers and open your browser to `http://localhost:5173`

Press **Ctrl+C** to stop.

## Prerequisites

If you prefer to install manually:

| Dependency | Version | Install |
|---|---|---|
| Python | 3.10+ | `brew install python@3.12` |
| Node.js | 18+ | `brew install node` |
| Claude Code CLI | latest | `npm install -g @anthropic-ai/claude-code` |

You must also authenticate the Claude CLI by running `claude` once in your terminal.

## Manual Start

If prerequisites are already installed:

```bash
./start.sh
```

## Architecture

- **Backend** — FastAPI (Python) on port 8000. Manages chat sessions, streams Claude responses over WebSocket, and processes document uploads.
- **Frontend** — React + Vite (TypeScript) on port 5173. Proxies API/WebSocket requests to the backend in dev mode.
- **Skills** — Plugin system for guided workflows (e.g., contract review). Each skill defines steps, prompts, and tools.
