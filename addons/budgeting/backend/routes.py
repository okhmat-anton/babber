"""
Budgeting Addon — Backend routes.

Manages income/expense entries, accounts, and loans with monthly history.
Collections: budget_entries, budget_accounts, budget_loans, budget_categories
"""
import logging
import uuid
from datetime import datetime, timezone, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user

logger = logging.getLogger("addon.budgeting")

router = APIRouter(
    prefix="/api/addons/budgeting",
    tags=["addon-budgeting"],
    dependencies=[Depends(get_current_user)],
)

# ── Collections ─────────────────────────────────────────────────────

ENTRIES_COL = "budget_entries"
ACCOUNTS_COL = "budget_accounts"
LOANS_COL = "budget_loans"
CATEGORIES_COL = "budget_categories"


# ── Pydantic Models ─────────────────────────────────────────────────

class BudgetEntryCreate(BaseModel):
    type: str = Field(..., description="income or expense")
    name: str
    amount: float
    category: str = ""
    is_recurring: bool = True
    is_paid: bool = False
    month_key: str = Field("", description="YYYY-MM format, auto-set if empty")
    notes: str = ""


class BudgetEntryUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    is_recurring: Optional[bool] = None
    is_paid: Optional[bool] = None
    notes: Optional[str] = None


class BudgetAccountCreate(BaseModel):
    name: str
    balance: float = 0.0
    is_credit_card: bool = False
    payment_date: Optional[int] = None  # Day of month
    notes: str = ""
    sort_order: int = 0


class BudgetAccountUpdate(BaseModel):
    name: Optional[str] = None
    balance: Optional[float] = None
    is_credit_card: Optional[bool] = None
    payment_date: Optional[int] = None
    notes: Optional[str] = None
    sort_order: Optional[int] = None


class BudgetLoanCreate(BaseModel):
    bank: str
    original_debt: float = 0.0
    remaining_debt: float
    monthly_payment: float
    payment_date: Optional[int] = None  # Day of month
    notes: str = ""
    sort_order: int = 0


class BudgetLoanUpdate(BaseModel):
    bank: Optional[str] = None
    original_debt: Optional[float] = None
    remaining_debt: Optional[float] = None
    monthly_payment: Optional[float] = None
    payment_date: Optional[int] = None
    notes: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryCreate(BaseModel):
    name: str
    type: str = "expense"  # income or expense
    icon: str = ""
    color: str = ""


# ── Helper ──────────────────────────────────────────────────────────

def _current_month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _make_id() -> str:
    return str(uuid.uuid4())


# ── Categories ──────────────────────────────────────────────────────

DEFAULT_EXPENSE_CATEGORIES = [
    "Housing", "Utilities", "Food", "Transport", "Insurance",
    "Healthcare", "Subscriptions", "Entertainment", "Education",
    "Clothing", "Personal", "Savings", "Debt", "Other",
]

DEFAULT_INCOME_CATEGORIES = [
    "Salary", "Freelance", "Business", "Investments", "Rental",
    "Side Hustle", "Gifts", "Refunds", "Other",
]


@router.get("/categories")
async def list_categories(
    type: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all budget categories, optionally filtered by type."""
    col = db[CATEGORIES_COL]
    count = await col.count_documents({})
    if count == 0:
        # Seed defaults
        docs = []
        for name in DEFAULT_EXPENSE_CATEGORIES:
            docs.append({"id": _make_id(), "name": name, "type": "expense", "icon": "", "color": ""})
        for name in DEFAULT_INCOME_CATEGORIES:
            docs.append({"id": _make_id(), "name": name, "type": "income", "icon": "", "color": ""})
        await col.insert_many(docs)
    query = {}
    if type:
        query["type"] = type
    items = await col.find(query, {"_id": 0}).sort("name", 1).to_list(500)
    return items


@router.post("/categories")
async def create_category(
    body: CategoryCreate,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    doc = {"id": _make_id(), **body.model_dump()}
    await db[CATEGORIES_COL].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/categories/{cat_id}")
async def delete_category(
    cat_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    result = await db[CATEGORIES_COL].delete_one({"id": cat_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Category not found")
    return {"ok": True}


# ── Budget Entries (Income / Expense) ───────────────────────────────

@router.get("/entries")
async def list_entries(
    month_key: Optional[str] = Query(None, description="YYYY-MM"),
    type: Optional[str] = Query(None, description="income or expense"),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List budget entries for a given month."""
    mk = month_key or _current_month_key()
    query: dict = {"month_key": mk}
    if type:
        query["type"] = type
    items = await db[ENTRIES_COL].find(query, {"_id": 0}).sort("sort_order", 1).to_list(1000)
    return {"items": items, "month_key": mk}


@router.post("/entries")
async def create_entry(
    body: BudgetEntryCreate,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    mk = body.month_key or _current_month_key()
    # Get next sort_order
    last = await db[ENTRIES_COL].find_one(
        {"month_key": mk, "type": body.type},
        sort=[("sort_order", -1)],
    )
    next_order = (last.get("sort_order", 0) + 1) if last else 0

    doc = {
        "id": _make_id(),
        "type": body.type,
        "name": body.name,
        "amount": body.amount,
        "category": body.category,
        "is_recurring": body.is_recurring,
        "is_paid": body.is_paid,
        "month_key": mk,
        "notes": body.notes,
        "sort_order": next_order,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[ENTRIES_COL].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/entries/{entry_id}")
async def update_entry(
    entry_id: str,
    body: BudgetEntryUpdate,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db[ENTRIES_COL].update_one({"id": entry_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Entry not found")
    doc = await db[ENTRIES_COL].find_one({"id": entry_id}, {"_id": 0})
    return doc


@router.patch("/entries/{entry_id}/toggle-paid")
async def toggle_entry_paid(
    entry_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Toggle the is_paid status of an entry."""
    doc = await db[ENTRIES_COL].find_one({"id": entry_id})
    if not doc:
        raise HTTPException(404, "Entry not found")
    new_val = not doc.get("is_paid", False)
    await db[ENTRIES_COL].update_one(
        {"id": entry_id},
        {"$set": {"is_paid": new_val, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"id": entry_id, "is_paid": new_val}


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    result = await db[ENTRIES_COL].delete_one({"id": entry_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Entry not found")
    return {"ok": True}


# ── Month Transition ────────────────────────────────────────────────

@router.post("/months/transition")
async def transition_month(
    target_month: str = Query(..., description="Target YYYY-MM to create"),
    source_month: Optional[str] = Query(None, description="Source YYYY-MM to copy from"),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """
    Create entries for a new month by copying recurring entries from source month.
    All paid statuses are reset. Non-recurring entries are NOT copied.
    """
    if not source_month:
        # Calculate previous month
        year, month = map(int, target_month.split("-"))
        if month == 1:
            source_month = f"{year - 1}-12"
        else:
            source_month = f"{year}-{month - 1:02d}"

    # Check if target already has entries
    existing = await db[ENTRIES_COL].count_documents({"month_key": target_month})
    if existing > 0:
        return {"message": f"Month {target_month} already has {existing} entries", "created": 0}

    # Copy recurring entries from source
    source_entries = await db[ENTRIES_COL].find(
        {"month_key": source_month, "is_recurring": True},
        {"_id": 0},
    ).to_list(1000)

    if not source_entries:
        return {"message": f"No recurring entries in {source_month}", "created": 0}

    new_entries = []
    for entry in source_entries:
        new_entry = {
            **entry,
            "id": _make_id(),
            "month_key": target_month,
            "is_paid": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        new_entry.pop("updated_at", None)
        new_entries.append(new_entry)

    await db[ENTRIES_COL].insert_many(new_entries)
    return {"message": f"Created {len(new_entries)} entries for {target_month}", "created": len(new_entries)}


@router.get("/months")
async def list_months(
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all months that have budget entries."""
    pipeline = [
        {"$group": {"_id": "$month_key"}},
        {"$sort": {"_id": -1}},
    ]
    results = await db[ENTRIES_COL].aggregate(pipeline).to_list(120)
    months = [r["_id"] for r in results if r["_id"]]
    # Ensure current month is always present
    current = _current_month_key()
    if current not in months:
        months.insert(0, current)
    return months


# ── Summary ─────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(
    month_key: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """
    Get budget summary for a month: totals, category breakdown,
    min daily earnings needed.
    """
    mk = month_key or _current_month_key()
    entries = await db[ENTRIES_COL].find(
        {"month_key": mk}, {"_id": 0}
    ).to_list(1000)

    total_income = 0.0
    total_expense = 0.0
    income_paid = 0.0
    expense_paid = 0.0
    income_by_cat: dict[str, float] = {}
    expense_by_cat: dict[str, float] = {}

    for e in entries:
        amt = e.get("amount", 0)
        cat = e.get("category", "Other") or "Other"
        if e.get("type") == "income":
            total_income += amt
            if e.get("is_paid"):
                income_paid += amt
            income_by_cat[cat] = income_by_cat.get(cat, 0) + amt
        else:
            total_expense += amt
            if e.get("is_paid"):
                expense_paid += amt
            expense_by_cat[cat] = expense_by_cat.get(cat, 0) + amt

    balance = total_income - total_expense

    # Remaining days in month
    year, month = map(int, mk.split("-"))
    today = date.today()
    if year == today.year and month == today.month:
        import calendar
        days_in_month = calendar.monthrange(year, month)[1]
        remaining_days = max(days_in_month - today.day + 1, 1)
    else:
        remaining_days = 1

    unpaid_expenses = total_expense - expense_paid
    remaining_income_needed = max(unpaid_expenses - (income_paid - expense_paid), 0)
    min_daily = remaining_income_needed / remaining_days if remaining_days > 0 else 0

    # Loan payments for this month
    loans = await db[LOANS_COL].find({}, {"_id": 0}).to_list(100)
    total_loan_payments = sum(l.get("monthly_payment", 0) for l in loans)

    return {
        "month_key": mk,
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "balance": round(balance, 2),
        "income_paid": round(income_paid, 2),
        "expense_paid": round(expense_paid, 2),
        "income_by_category": {k: round(v, 2) for k, v in sorted(income_by_cat.items())},
        "expense_by_category": {k: round(v, 2) for k, v in sorted(expense_by_cat.items())},
        "remaining_days": remaining_days,
        "min_daily_earnings": round(min_daily, 2),
        "total_loan_payments": round(total_loan_payments, 2),
    }


# ── Accounts ────────────────────────────────────────────────────────

@router.get("/accounts")
async def list_accounts(
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    items = await db[ACCOUNTS_COL].find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)
    return items


@router.post("/accounts")
async def create_account(
    body: BudgetAccountCreate,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    doc = {"id": _make_id(), **body.model_dump(), "created_at": datetime.now(timezone.utc).isoformat()}
    await db[ACCOUNTS_COL].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/accounts/{account_id}")
async def update_account(
    account_id: str,
    body: BudgetAccountUpdate,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    result = await db[ACCOUNTS_COL].update_one({"id": account_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Account not found")
    doc = await db[ACCOUNTS_COL].find_one({"id": account_id}, {"_id": 0})
    return doc


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    result = await db[ACCOUNTS_COL].delete_one({"id": account_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Account not found")
    return {"ok": True}


# ── Loans ───────────────────────────────────────────────────────────

@router.get("/loans")
async def list_loans(
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    items = await db[LOANS_COL].find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)
    return items


@router.post("/loans")
async def create_loan(
    body: BudgetLoanCreate,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    doc = {"id": _make_id(), **body.model_dump(), "created_at": datetime.now(timezone.utc).isoformat()}
    await db[LOANS_COL].insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/loans/{loan_id}")
async def update_loan(
    loan_id: str,
    body: BudgetLoanUpdate,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    result = await db[LOANS_COL].update_one({"id": loan_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Loan not found")
    doc = await db[LOANS_COL].find_one({"id": loan_id}, {"_id": 0})
    return doc


@router.delete("/loans/{loan_id}")
async def delete_loan(
    loan_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    result = await db[LOANS_COL].delete_one({"id": loan_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Loan not found")
    return {"ok": True}


# ── Agent-Readable Summary ──────────────────────────────────────────

@router.get("/agent-summary")
async def agent_summary(
    month_key: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """
    Human-readable budget summary for agent consumption.
    """
    mk = month_key or _current_month_key()
    summary = await get_summary(month_key=mk, db=db)
    entries = await db[ENTRIES_COL].find(
        {"month_key": mk}, {"_id": 0}
    ).to_list(1000)
    accounts = await db[ACCOUNTS_COL].find({}, {"_id": 0}).to_list(100)
    loans = await db[LOANS_COL].find({}, {"_id": 0}).to_list(100)

    lines = [f"=== Budget Summary for {mk} ==="]
    lines.append(f"Total Income: ${summary['total_income']:,.2f} (received: ${summary['income_paid']:,.2f})")
    lines.append(f"Total Expenses: ${summary['total_expense']:,.2f} (paid: ${summary['expense_paid']:,.2f})")
    lines.append(f"Balance: ${summary['balance']:,.2f}")
    lines.append(f"Min Daily Earnings Needed: ${summary['min_daily_earnings']:,.2f}")
    lines.append(f"Remaining Days: {summary['remaining_days']}")
    lines.append("")

    # Income breakdown
    income_entries = [e for e in entries if e.get("type") == "income"]
    if income_entries:
        lines.append("--- Income ---")
        for e in income_entries:
            paid = "PAID" if e.get("is_paid") else "UNPAID"
            rec = "recurring" if e.get("is_recurring") else "one-time"
            lines.append(f"  [{paid}] {e['name']}: ${e['amount']:,.2f} ({e.get('category', '')}, {rec})")

    # Expense breakdown
    expense_entries = [e for e in entries if e.get("type") == "expense"]
    if expense_entries:
        lines.append("--- Expenses ---")
        for e in expense_entries:
            paid = "PAID" if e.get("is_paid") else "UNPAID"
            rec = "recurring" if e.get("is_recurring") else "one-time"
            lines.append(f"  [{paid}] {e['name']}: ${e['amount']:,.2f} ({e.get('category', '')}, {rec})")

    # Category summary
    if summary["expense_by_category"]:
        lines.append("")
        lines.append("--- Expenses by Category ---")
        for cat, amt in summary["expense_by_category"].items():
            lines.append(f"  {cat}: ${amt:,.2f}")

    # Accounts
    if accounts:
        lines.append("")
        lines.append("--- Accounts ---")
        for a in accounts:
            cc = " [Credit Card]" if a.get("is_credit_card") else ""
            pd = f" (payment day: {a['payment_date']})" if a.get("payment_date") else ""
            lines.append(f"  {a['name']}: ${a.get('balance', 0):,.2f}{cc}{pd}")

    # Loans
    if loans:
        lines.append("")
        lines.append("--- Loans ---")
        for l in loans:
            pd = f" (payment day: {l['payment_date']})" if l.get("payment_date") else ""
            lines.append(f"  {l['bank']}: debt ${l.get('remaining_debt', 0):,.2f}, monthly ${l.get('monthly_payment', 0):,.2f}{pd}")

    return {"summary": "\n".join(lines)}
