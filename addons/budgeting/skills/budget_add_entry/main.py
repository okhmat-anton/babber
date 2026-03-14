import uuid
from datetime import datetime, timezone


async def execute(
    type: str = "expense",
    name: str = "",
    amount: float = 0,
    category: str = "",
    is_recurring: bool = True,
    is_paid: bool = False,
    month_key: str = "",
):
    """Add an income or expense entry to the budget."""
    if not name:
        return {"error": "Entry name is required"}
    if amount <= 0:
        return {"error": "Amount must be greater than 0"}
    if type not in ("income", "expense"):
        return {"error": "Type must be 'income' or 'expense'"}

    from app.database import get_mongodb

    if not month_key:
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        db = get_mongodb()
        col = db["budget_entries"]

        # Get next sort_order
        last = await col.find_one(
            {"month_key": month_key, "type": type},
            sort=[("sort_order", -1)],
        )
        next_order = (last.get("sort_order", 0) + 1) if last else 0

        doc = {
            "id": str(uuid.uuid4()),
            "type": type,
            "name": name,
            "amount": amount,
            "category": category,
            "is_recurring": is_recurring,
            "is_paid": is_paid,
            "month_key": month_key,
            "notes": "",
            "sort_order": next_order,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await col.insert_one(doc)

        return {
            "success": True,
            "message": f"Added {type} entry: {name} ${amount:,.2f} ({category or 'no category'}) for {month_key}",
        }
    except Exception as e:
        return {"error": f"Failed to add entry: {e}"}
