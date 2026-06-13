import json
import os
import asyncio
import httpx
from pydantic import BaseModel
import google.generativeai as genai
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

class AgentState(BaseModel):
    user_message:str
    intent: Optional[str] = None
    tool_result: Optional[dict] = None
    final_response: Optional[str] = None

def route_intent(state: AgentState) -> AgentState:
        message = state.user_message.lower()
        if "supplier" in message or "vendor" in message:
         state.intent = "find_supplier"
        elif "shipment" in message or "order" in message or "track" in message:
         state.intent = "check_shipment"
        else:
         state.intent = "unknown"
        return state

async def find_supplier(category : str) -> dict:
   try:
    suppliers = [
       {"name":"Kerala Logistics Co.","category":"cold_chain","rating":9.1,"location":"Kochi"},
       {"name":"TN Freight Hub","category":"freight","rating":8.3,"location":"Chennai"},
       {"name":"Mumbai Cargo Ltd.","category":"cold_chain","rating":8.7,"location":"Mumbai"},
       {"name":"Delhi Supply Chain","category":"last_mile","rating":7.9,"location":"Delhi"},
       {"name":"Bangalore Logistics","category":"freight","rating":8.1,"location":"Bangalore"}]
    matched = []
    for s in suppliers:
       if s["category"] == category.lower():
          matched.append(s)
    matched.sort(key =lambda x : x["rating"], reverse = True)
    if matched:
       return {"status" : "success", "suppliers" : matched}
    else:
       return {"status": "no result", "suppliers" : []}
   except Exception as e:
    return {"status" : "error", "message" : f"Tool failed : {e}"}
   
# ── Tool 2 — Check Shipment ────────────────────────────
async def check_shipment(order_id: str) -> dict:
    try:
        # Mock shipment database
        shipments = [
            {"order_id": "ORD-001", "status": "delivered",  "eta_days": 0, "location": "Kochi"},
            {"order_id": "ORD-002", "status": "in_transit", "eta_days": 2, "location": "Mumbai"},
            {"order_id": "ORD-003", "status": "in_transit", "eta_days": 5, "location": "Delhi"},
            {"order_id": "ORD-004", "status": "pending",    "eta_days": 7, "location": "Chennai"}
        ]

        for s in shipments:
            if s["order_id"] == order_id.upper():
                return {"status": "success", "shipment": s}

        return {"status": "not_found", "message": f"No shipment found for {order_id}"}

    except Exception as e:
        return {"status": "error", "message": f"Tool failed: {e}"}
    
# ── Orchestrator — calls the right tool based on intent ──
async def run_tool(state: AgentState) -> AgentState:
    intent = state.intent
    message = state.user_message.lower()

    if intent == "find_supplier":
        # Extract category from message
        if "cold chain" in message or "cold_chain" in message:
            category = "cold_chain"
        elif "freight" in message:
            category = "freight"
        elif "last mile" in message or "last_mile" in message:
            category = "last_mile"
        else:
            category = "cold_chain"   # default category

        state.tool_result = await find_supplier(category)

    elif intent == "check_shipment":
        # Extract order ID from message
        # Look for pattern like ORD-001 in the message
        words = message.upper().split()
        order_id = None
        for word in words:
            if word.startswith("ORD-"):
                order_id = word
                break

        if order_id:
            state.tool_result = await check_shipment(order_id)
        else:
            state.tool_result = {
                "status": "error",
                "message": "Please provide an order ID (e.g. ORD-001)"
            }

    else:
        state.tool_result = {
            "status": "unknown",
            "message": "I can help with finding suppliers or tracking shipments."
        }

    return state
   
async def generate_response(state: AgentState) -> AgentState:
   try:
      genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
      model = genai.GenerativeModel("gemini-2.5-flash")

      prompt = f"""You are a helpful procurement assistant.
      The user asked: {state.user_message}

      Here is the data retrived by the tool:
      {json.dumps(state.tool_result, indent = 2)}

      Write a clear, helpful response to the user based on this data.
      Keep it concise - 3 to 5 sentences maximum."""

      response = model.generate_content(prompt)
      state.final_response = response.text
      return state
   
   except Exception as e:
      state.final_response = f"Could not generate response: {e}"
      return state


# ── Main Runner ───────────────────────────────────────
if __name__ == "__main__":
    async def run_agent():
        print("Procurement Agent ready.")
        print("Try: 'Find me a freight supplier'")
        print("Or:  'Track my order ORD-002'")
        print("Type 'quit' to exit.\n")

        while True:
            user_input = input("You: ")

            if user_input.lower() == "quit":
                print("Goodbye.")
                break

            # Build state
            state = AgentState(user_message=user_input)

            # Step 1 — route
            state = route_intent(state)
            print(f"[Intent: {state.intent}]")

            # Step 2 — run the right tool automatically
            state = await run_tool(state)
            print(f"[Tool status: {state.tool_result.get('status')}]")

            # Step 3 — generate natural language response
            state = await generate_response(state)
            print(f"\nAgent: {state.final_response}\n")

    asyncio.run(run_agent())