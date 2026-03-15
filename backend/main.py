import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from models import Session, Message
from claude_runner import ClaudeRunner
from skills import list_skills, get_skill, register_skill
from skills.models import SkillSession

# Import skills to register them
import skills.contract_review  # noqa: F401

app = FastAPI(title="Claude Code Web Wrapper")

UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store
sessions: dict[str, Session] = {}
# Active runners per session
runners: dict[str, ClaudeRunner] = {}
# Skill sessions
skill_sessions: dict[str, SkillSession] = {}


@app.get("/api/sessions")
async def list_sessions():
    return [
        {
            "id": s.id,
            "title": s.title,
            "createdAt": s.created_at,
            "messageCount": len(s.messages),
            "workingDirectory": s.working_directory,
        }
        for s in sorted(sessions.values(), key=lambda x: x.created_at, reverse=True)
    ]


@app.post("/api/sessions")
async def create_session(working_directory: str = ""):
    session = Session(
        id=str(uuid.uuid4()),
        working_directory=working_directory or os.getcwd(),
    )
    sessions[session.id] = session
    return {"id": session.id, "title": session.title, "createdAt": session.created_at}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}, 404
    return session.model_dump()


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id in runners:
        await runners[session_id].cancel()
        del runners[session_id]
    sessions.pop(session_id, None)
    return {"ok": True}


@app.get("/api/directories")
async def list_directories(path: str = Query(default="~")):
    target = Path(path).expanduser().resolve()
    if not target.is_dir():
        return {"error": "Not a directory", "path": str(target)}
    try:
        dirs = []
        for entry in sorted(target.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                dirs.append({"name": entry.name, "path": str(entry)})
        return {"path": str(target), "parent": str(target.parent), "directories": dirs}
    except PermissionError:
        return {"error": "Permission denied", "path": str(target)}


# ── Skill API endpoints ────────────────────────────────────────


@app.get("/api/skills")
async def get_skills():
    return list_skills()


@app.post("/api/skills/{skill_id}/sessions")
async def create_skill_session(skill_id: str):
    skill = get_skill(skill_id)
    if not skill:
        return {"error": f"Skill '{skill_id}' not found"}

    ss = SkillSession(
        id=str(uuid.uuid4()),
        skill_id=skill_id,
        current_stage=skill.stages[0],
    )
    skill_sessions[ss.id] = ss

    # Get initial prompt for first stage
    prompt = await skill.get_stage_prompt(ss)

    return {
        "id": ss.id,
        "skillId": skill_id,
        "stage": ss.current_stage,
        "stages": skill.stages,
        "initialPrompt": prompt.model_dump(),
    }


@app.get("/api/skills/sessions/{session_id}")
async def get_skill_session(session_id: str):
    ss = skill_sessions.get(session_id)
    if not ss:
        return {"error": "Skill session not found"}
    return ss.model_dump()


@app.post("/api/skills/sessions/{session_id}/upload")
async def upload_skill_file(session_id: str, file: UploadFile = File(...)):
    ss = skill_sessions.get(session_id)
    if not ss:
        return {"error": "Skill session not found"}

    # Save uploaded file
    upload_dir = UPLOADS_DIR / ss.id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "filename": file.filename,
        "path": str(file_path),
        "size": len(content),
    }


@app.post("/api/skills/sessions/{session_id}/message")
async def skill_message(session_id: str, content: str = Form(""), uploaded_file_path: str = Form("")):
    ss = skill_sessions.get(session_id)
    if not ss:
        return {"error": "Skill session not found"}

    skill = get_skill(ss.skill_id)
    if not skill:
        return {"error": "Skill not found"}

    file_info = None
    if uploaded_file_path:
        file_info = {
            "path": uploaded_file_path,
            "filename": Path(uploaded_file_path).name,
        }

    responses = await skill.handle_message(ss, content, file_info)
    return {
        "responses": [r.model_dump() for r in responses],
        "stage": ss.current_stage,
        "context": {
            "approved_count": len(ss.approved_revisions),
            "pending_count": len(ss.pending_revisions),
            "revision_index": ss.revision_index,
        },
    }


@app.get("/api/skills/sessions/{session_id}/transcript")
async def get_skill_transcript(session_id: str):
    ss = skill_sessions.get(session_id)
    if not ss:
        return {"error": "Skill session not found"}
    return {"transcript": [e.model_dump() for e in ss.transcript]}


@app.get("/api/skills/sessions/{session_id}/download/{file_key}")
async def download_skill_file(session_id: str, file_key: str):
    ss = skill_sessions.get(session_id)
    if not ss:
        return {"error": "Skill session not found"}

    file_path = ss.files.get(file_key)
    if not file_path or not os.path.exists(file_path):
        return {"error": f"File '{file_key}' not found"}

    return FileResponse(
        path=file_path,
        filename=Path(file_path).name,
        media_type="application/octet-stream",
    )


@app.get("/api/playbooks")
async def list_playbooks():
    pb_dir = Path.home() / ".claude-code-web" / "playbooks"
    if not pb_dir.exists():
        return []
    playbooks = []
    for f in sorted(pb_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(f) as fh:
                data = json.load(fh)
            playbooks.append({
                "filename": f.name,
                "name": data.get("name", f.stem),
                "date": data.get("date", ""),
                "rule_count": len(data.get("rules", [])),
                "party_role": data.get("party_role", ""),
            })
        except (json.JSONDecodeError, KeyError):
            pass
    return playbooks


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # Ensure session exists
    if session_id not in sessions:
        sessions[session_id] = Session(
            id=session_id, working_directory=os.getcwd()
        )

    session = sessions[session_id]

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            if data["type"] == "cancel":
                if session_id in runners:
                    await runners[session_id].cancel()
                await websocket.send_json({"type": "cancelled"})
                continue

            if data["type"] == "prompt":
                prompt = data["content"]
                model = data.get("model", "sonnet")
                working_dir = data.get("workingDir", session.working_directory)
                auto_approve = data.get("autoApprove", True)

                # Update session working directory
                session.working_directory = working_dir

                # Save user message
                session.messages.append(Message(role="user", content=prompt))

                runner = ClaudeRunner()
                runners[session_id] = runner

                # Determine if we should resume an existing Claude session
                resume_id = session.claude_session_id

                assistant_content = ""
                tool_uses = []

                try:
                    async for event in runner.run(
                        prompt=prompt,
                        session_id=session_id,
                        model=model,
                        working_dir=working_dir,
                        auto_approve=auto_approve,
                        resume_session=resume_id,
                    ):
                        # Forward event to client
                        await websocket.send_json(event)

                        # Track content for session history
                        etype = event.get("type", "")

                        if etype == "assistant":
                            # Final assistant message from stream-json
                            msg = event.get("message", {})
                            for block in msg.get("content", []):
                                if block.get("type") == "text":
                                    assistant_content = block.get("text", "")
                                elif block.get("type") == "tool_use":
                                    tool_uses.append({
                                        "id": block.get("id", ""),
                                        "name": block.get("name", ""),
                                        "input": block.get("input", {}),
                                    })

                            # Capture Claude's session ID for resuming
                            sid = event.get("sessionId") or msg.get("session_id")
                            if sid:
                                session.claude_session_id = sid

                        elif etype == "result":
                            # Result message contains final text and session info
                            sid = event.get("session_id") or event.get("sessionId")
                            if sid:
                                session.claude_session_id = sid
                            result_text = event.get("result", "")
                            if result_text and not assistant_content:
                                assistant_content = result_text

                    # Auto-generate session title from first message
                    if len(session.messages) == 1 and session.title == "New Chat":
                        session.title = prompt[:60] + ("..." if len(prompt) > 60 else "")

                    # Save assistant message
                    session.messages.append(
                        Message(
                            role="assistant",
                            content=assistant_content,
                            tool_uses=tool_uses,
                        )
                    )

                    await websocket.send_json({
                        "type": "done",
                        "session_id": session_id,
                        "claude_session_id": session.claude_session_id,
                    })

                except asyncio.CancelledError:
                    await websocket.send_json({"type": "cancelled"})
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": str(e)},
                    })
                finally:
                    runners.pop(session_id, None)

    except WebSocketDisconnect:
        if session_id in runners:
            await runners[session_id].cancel()
            runners.pop(session_id, None)


# Serve static frontend build if it exists
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
