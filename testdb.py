from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("DATABASE_URL")
print("URL found:", url)

try:
    engine = create_engine(url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("Connection successful:", result.fetchone())
except Exception as e:
    print("Connection failed:", e)