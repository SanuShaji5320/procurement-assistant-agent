import json
import os
import asyncio
import selectors
from typing import Optional, Annotated
from typing_extensions import TypedDict
import operator
from dotenv import load_dotenv
load_dotenv()
DB_URL = os.getenv("DATABASE_URL", "")
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)


from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from database import get_shipment_by_order_id, get_suppliers_by_category

# state_____________________________________________________
class AgentState(TypedDict):
    user_message  :str
    intent: Optional[str]
    tool_result: Optional[dict]
    final_response: Optional[str]
    messages: Annotated[list, operator.add]

#LLM________________________________________________________
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

#Node 1 _____Route Intent____________________________________
async def route_intent(state: AgentState) -> dict:
    message = state["user_message"]
    has_history = len(state.get("messages", [])) > 0

    classification_prompt = f"""You are an intent classifier for a procurement assistant.
Classify the user message into exactly one of these intents:

- find_supplier: user wants to find, discover, or get recommendations for suppliers or vendors
- check_shipment: user wants to track, check status, or get updates on a shipment or order
- follow_up: user is asking a follow-up question related to previous conversation
- unknown: message doesn't relate to suppliers or shipments

User message: "{message}"
Has conversation history: {has_history}

Reply with only one word — the intent label. Nothing else."""

    try:
        response = await llm.ainvoke([HumanMessage(content=classification_prompt)])
        intent = response.content.strip().lower()

        # Validate — fallback if LLM returns unexpected value
        valid_intents = {"find_supplier", "check_shipment", "follow_up", "unknown"}
        if intent not in valid_intents:
            intent = "follow_up" if has_history else "unknown"

    except Exception:
        # If LLM call fails, fall back to keyword matching
        msg = message.lower()
        if "supplier" in msg or "vendor" in msg:
            intent = "find_supplier"
        elif "shipment" in msg or "order" in msg or "track" in msg:
            intent = "check_shipment"
        elif has_history:
            intent = "follow_up"
        else:
            intent = "unknown"

    return {
        "intent": intent,
        "messages": [{"role": "user", "content": message}]
    }

#Node 2 ______Find Supplier _________________________________
async def find_supplier_node(state: AgentState) -> dict:
    message = state["user_message"].lower()

    if "cold chain" in message or "cold_chain" in message:
        category = "cold_chain"
    elif "freight" in message:
        category = "freight"
    elif "last mile" in message or "last_mile" in message:
        category = "last_mile"
    else:
        category = "cold_chain"
    
    try:
        suppliers = get_suppliers_by_category(category)
        if suppliers:
            result = {"status": "success", "suppliers": suppliers}
        else:
            result = {"status": "no_results", "suppliers": []}
    except Exception as e:
        result = {"status": "error", "message": f"Tool failed: {e}"}
    return {"tool_result": result}

#Node 3 ___Check Shipment__________________________________________
async def check_shipment_node(state: AgentState) -> dict:
    message = state["user_message"].upper().split()

    order_id = None
    for word in message:
        if word.startswith("ORD-"):
            order_id = word
            break
    
    if not order_id:
        return{"tool_result": {
            "status":"error",
            "message":"Please provide an order ID (e.g. ORD-001)"
        }}
    try:
        shipment = get_shipment_by_order_id(order_id)

        if shipment:
            return {"tool_result": {"status": "success", "shipment": shipment}}
        else:
            return {"tool_result": {
                "status": "not_found",
                "message": f"No shipment found for {order_id}"
            }}
    
    except Exception as e:
        return{"tool_result": {
            "status":"error",
            "message": f"Tool failed: {e}"
        }}
#follow up node__________________________________________________________    
async def follow_up_node(state: AgentState) -> dict:
    return {"tool_result": {
        "status": "follow_up",
        "message": "Answer from conversation history only."
    }}
# ── Node 4 — Unknown Intent ────────────────────────────────────
def unknown_node(state: AgentState) -> dict:
    return {"tool_result": {
        "status": "unknown",
        "message": "I can help with finding suppliers or tracking shipments."
    }}

#Node 5____Generate Response ___________________________
async def generate_response_node(state: AgentState) -> dict:
    try:
        history = ""
        if len(state["messages"]) > 1:
            history = "Conversation so far :\n"
            for msg in state["messages"][:-1]:
                role = "User" if msg["role"] == "user" else "Agent"
                history += f"{role}: {msg['content']}\n"
        prompt = f"""You are a helpful procurement assistant.
        {history}
        The user asked: {state["user_message"]}
Here is the data retrieved by the tool:
{json.dumps(state["tool_result"], indent=2)}

Write a clear, helpful response based on this data and conversation history.
keep it concise - 3 to 5 sentences maximum."""
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        final= response.content
        return{
            "final_response": final,
            "messages": [{"role":"assistant", "content": final}]
        }
    
    except Exception as e:
        error_msg = f"Could not generate response: {e}"
        return {"final_response": error_msg,
                "messages": [{"role":"assistant", "content": error_msg}]}   

#Build the Graph __________________________________________________
def route_after_intent(state: AgentState) -> str:
    return state["intent"]

#Compile __________________________________________________________
builder = StateGraph(AgentState)

#Register nodes
builder.add_node("route_intent", route_intent)
builder.add_node("find_supplier", find_supplier_node)
builder.add_node("check_shipment", check_shipment_node)
builder.add_node("unknown", unknown_node)
builder.add_node("generate_response", generate_response_node)
builder.add_node("follow_up", follow_up_node)

# Entry point ___________________________________________
builder.add_edge(START, "route_intent")

#Conditional branching after intent detection____________________
builder.add_conditional_edges(
    "route_intent",
    route_after_intent,
    {
        "find_supplier": "find_supplier",
        "check_shipment": "check_shipment",
        "follow_up": "follow_up",
        "unknown": "unknown"
    }
)
# All tools converge into response generation___________________
builder.add_edge("find_supplier", "generate_response")
builder.add_edge("check_shipment", "generate_response")
builder.add_edge("unknown", "generate_response")
builder.add_edge("follow_up", "generate_response")

#Exit___________________________________________________
builder.add_edge("generate_response", END)


#Conversation Loop_____________________________________
async def run_agent():
    print("Procurement Agent v2.0 ready.")
    print("Try: 'Find me a freight supplier'")
    print("Or:  'Track my order ORD-002'")
    print("Type 'quit' to exit.\n")

    thread_config = {"configurable": {"thread_id": "session_1"}}

    async with AsyncPostgresSaver.from_conn_string(DB_URL) as checkpointer:
        await checkpointer.setup()
        pg_graph = builder.compile(checkpointer=checkpointer)

        while True:
            user_input = input("You: ")

            if user_input.lower() == "quit":
                print("Goodbye.")
                break

            result = await pg_graph.ainvoke(
                {
                    "user_message":  user_input,
                    "intent":        None,
                    "tool_result":   None,
                    "final_response": None
                },
                config=thread_config
            )

            print(f"[Intent:  {result['intent']}]")
            print(f"[Status:  {result['tool_result'].get('status')}]")
            print(f"[Messages in history: {len(result['messages'])}]")
            print(f"\nAgent: {result['final_response']}\n")

import selectors

# Module-level graph for API use (no checkpointer — stateless)
graph = builder.compile()
if __name__ == "__main__":
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_agent())
    finally:
        loop.close()