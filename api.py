import os
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from agent2 import builder, AgentState

# App_______________________________________________
app = FastAPI(
    title="Procurement Assistant API",
    description="Agentic AI procurement assistant - supplier discovery and shipment tracking",
    version="2.0"
)
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "https://sanushaji5320.github.io",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from contextlib import asynccontextmanager

from agent2 import DB_URL

# Global graph reference____________________________
pg_graph = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pg_graph
    try:
        async with AsyncPostgresSaver.from_conn_string(DB_URL) as checkpointer:
            await checkpointer.setup()
            pg_graph = builder.compile(checkpointer=checkpointer)
            print("✅ pg_graph initialized successfully")
            yield
    except Exception as e:
        print(f"❌ LIFESPAN STARTUP FAILED: {e}")
        raise


# Health Check______________________________________
@app.get("/")
async def health_check():
    return {
        "status": "running",
        "agent": "Procurement Assistant v2.0",
        "endpoints": ["/chat", "/history/{thread_id}"]
    }

# Request/Response Models___________________________
class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = "default"

class ChatResponse(BaseModel):
    reply: str
    intent: str
    status: str
    thread_id: str
    messages_in_history: int

# Chat Endpoint_____________________________________
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        result = await pg_graph.ainvoke(
            {
                "user_message": request.message,
                "intent": None,
                "tool_result": None,
                "final_response": None
            },
            config={"configurable": {"thread_id": request.thread_id}}
        )
        return ChatResponse(
            reply=result["final_response"],
            intent=result["intent"],
            status=result["tool_result"].get("status"),
            thread_id=request.thread_id,
            messages_in_history=len(result["messages"])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

# History Endpoint__________________________________
@app.get("/history/{thread_id}")
async def get_history(thread_id: str):
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = await pg_graph.aget_state(config)

        if not state or not state.values:
            raise HTTPException(
                status_code=404,
                detail=f"No conversation found for thread_id: {thread_id}"
            )
        messages = state.values.get("messages", [])

        if not messages:
            raise HTTPException(
                status_code=404,
                detail=f"No messages found for thread_id: {thread_id}"
            )
        return {
            "thread_id": thread_id,
            "message_count": len(messages),
            "messages": messages
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching history: {e}")