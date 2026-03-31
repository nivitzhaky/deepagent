import asyncio
import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent import DeepAgent

load_dotenv()

app = FastAPI(title="DeepAgent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE_DIR = Path(__file__).parent.parent / "workspace"
WORKSPACE_DIR.mkdir(exist_ok=True)

FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/")
async def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        assignment = data.get("assignment", "").strip()
        language = data.get("language", "python")
        model_provider = data.get("model_provider", "openai")
        model_name = data.get("model_name", "gpt-4o")
        max_iterations = int(data.get("max_iterations", 10))

        if not assignment:
            await websocket.send_json({"type": "error", "data": {"message": "Assignment is required"}})
            return

        session_id = str(uuid.uuid4())[:8]
        session_dir = WORKSPACE_DIR / session_id
        session_dir.mkdir(exist_ok=True)

        agent = DeepAgent(
            websocket=websocket,
            session_dir=session_dir,
            model_provider=model_provider,
            model_name=model_name,
            max_iterations=max_iterations,
        )

        await agent.run(assignment=assignment, language=language)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "data": {"message": str(e)}})
        except Exception:
            pass


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
