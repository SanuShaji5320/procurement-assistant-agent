import requests
import httpx
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import json

print("✓ All libraries imported successfully")

class TestAgent(BaseModel):
    name: str
    domain: str

agent = TestAgent(name="Sanu", domain="logistics")
print(f"✓ Pydantic working — {agent.name}, {agent.domain}")

data = {"status": "ready", "modules_completed": 10}
json_string = json.dumps(data)
parsed = json.loads(json_string)
print(f"✓ JSON working — {parsed['status']}")

load_dotenv()
print("✓ Dotenv working")

print("\nSetup complete. Ready to build.")