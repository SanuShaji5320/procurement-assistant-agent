import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from agent2 import graph, AgentState

#App_______________________________________________
app = FastAPI(
    title="Procurement Assistant API",
    description="Agentic AI procurement assistant - supplier discovery and shipment tracking",
    version="2.0"
)


#Health Check_______________________________________
@app.get("/")
async def health_check():
    return{
        "status": "running",
        "agent": "Procurement Assistant v2.0",
        "endpoints": ["/chat","/history/{thread_id}"]
    }

#Request /Response Models____________________________
class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = "default"

class ChatResponse(BaseModel):
    reply: str
    intent: str
    status: str
    thread_id: str
    messages_in_history: int

# Chat Endpoint______________________________________
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        result = await graph.ainvoke(
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
    
#__History Endpoint ______________________________________
@app.get("history/{thread_id}")
async def get_history(thread_id: str):
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = graph.get_state(config)

        if not state or not state.values:
            raise HTTPException(
                status_code=404,
                detail=f"No conversation found for thread_id: {thread_id}"
            )
        messages = state.values.get("messages",[])

        if not messages:
            raise HTTPException(
                status_code=404,
                detail=f"No messages found for thread_id: {thread_id}"
            )
        return{
            "thread_id": thread_id,
            "message_count": len(messages),
            "messages": messages
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching history: {e}")