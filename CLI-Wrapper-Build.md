# Claude Code CLI Wrapper — Build Summary

## Overview

A web-based interface that wraps the Claude Code CLI, providing a browser-based chat experience powered by the Claude CLI running locally.

## Tech Stack

- **Backend**: Python / FastAPI
- **Frontend**: React + TypeScript (Vite)
- **Communication**: WebSocket for real-time streaming
- **CLI Integration**: `claude_runner.py` spawns Claude Code CLI processes

## Architecture

```
Browser (React) <--WebSocket--> FastAPI Backend <--subprocess--> Claude Code CLI
```

## Backend (`backend/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app with WebSocket endpoints, session management, REST API routes |
| `claude_runner.py` | Spawns and manages Claude Code CLI processes, streams output back |
| `models.py` | Pydantic data models for sessions and messages |
| `document_processor.py` | Handles document upload and processing |
| `redline_generator.py` | Generates redline/diff comparisons for documents |
| `requirements.txt` | Python dependencies |
| `skills/__init__.py` | Skills framework initialization |
| `skills/models.py` | Data models for the skills system |
| `skills/contract_review.py` | Contract Review & Revise skill — guided workflow for legal docs |

## Frontend (`frontend/`)

### Core Files

| File | Purpose |
|------|---------|
| `src/App.tsx` | Main app component — manages sessions, routing between chat and skills |
| `src/main.tsx` | React entry point |
| `src/types.ts` | TypeScript type definitions (Session, Settings, Message, etc.) |
| `src/index.css` | Global styles |
| `index.html` | HTML entry point |
| `vite.config.ts` | Vite build configuration |
| `tsconfig.json` | TypeScript configuration |

### Components (`src/components/`)

| Component | Purpose |
|-----------|---------|
| `Sidebar.tsx` | Session list, working directory picker, settings (auto-approve toggle) |
| `ChatArea.tsx` | Displays chat messages with streaming support |
| `InputArea.tsx` | Message input with model selector and cancel button |
| `MessageBubble.tsx` | Individual message rendering (user and assistant) |
| `CodeBlock.tsx` | Syntax-highlighted code block rendering |
| `ToolUseBlock.tsx` | Displays Claude's tool use (file edits, bash commands, etc.) |
| `SkillLauncher.tsx` | Modal to browse and launch available skills |
| `SkillFlow.tsx` | Guided multi-stage skill workflow UI |
| `SkillMessage.tsx` | Message rendering within skill flows |
| `StageProgress.tsx` | Progress indicator for skill stages |
| `FileUpload.tsx` | Drag-and-drop file upload component |
| `ConfidenceBadge.tsx` | Displays confidence level badges for skill outputs |

### Hooks (`src/hooks/`)

| Hook | Purpose |
|------|---------|
| `useWebSocket.ts` | Manages WebSocket connection, message streaming, and reconnection |
| `useSkillSession.ts` | Manages skill lifecycle — start, message, upload, download, close |

## Features

- **Chat sessions**: Create, switch, and delete multiple chat sessions
- **Real-time streaming**: Responses stream in via WebSocket as Claude generates them
- **Model selection**: Choose between Claude models (e.g., Sonnet)
- **Working directory**: Set the directory Claude operates in
- **Auto-approve**: Toggle automatic approval for Claude's tool use
- **Skills framework**: Guided multi-step workflows (e.g., Contract Review & Revise)
- **File upload**: Upload documents for skill-based processing
- **Tool use display**: See what tools Claude is using (file edits, bash commands)

## Setup & Running

| Script | Purpose |
|--------|---------|
| `setup.sh` | Automated macOS setup — installs dependencies, configures environment |
| `start.sh` | Launches both backend and frontend servers |

## File Backup Location

All source files are preserved in:
- **Git history**: `arikuchinsky/Generic` repo, commit `71f8dd3`
- **Local copy**: `/home/user/.claude/CLI Wrapper/`
