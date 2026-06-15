import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# ── Engine ─────────────────────────────────────────────────────
db_url = os.getenv("DATABASE_URL", "")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
if db_url.startswith("postgresql://") and "+psycopg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(db_url)

# ── Query Functions ────────────────────────────────────────────
def get_suppliers_by_category(category: str) -> list:
    query = text("""
        SELECT name, category, rating, location
        FROM suppliers
        WHERE category = :category
        ORDER BY rating DESC
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"category": category})
        rows = result.fetchall()
        return [
            {
                "name":     row.name,
                "category": row.category,
                "rating":   float(row.rating),
                "location": row.location
            }
            for row in rows
        ]

def get_shipment_by_order_id(order_id: str) -> dict | None:
    query = text("""
        SELECT order_id, status, eta_days, location
        FROM shipments
        WHERE order_id = :order_id
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"order_id": order_id})
        row = result.fetchone()
        if row:
            return {
                "order_id": row.order_id,
                "status":   row.status,
                "eta_days": row.eta_days,
                "location": row.location
            }
        return None