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
    is_credit_card: bool = False
    frequency: str = Field("once", description="once, daily, or weekly")
    month_key: str = Field("", description="YYYY-MM format, auto-set if empty")
    day_of_month: Optional[int] = Field(None, ge=1, le=31, description="Day of month for this payment/income")
    notes: str = ""


class BudgetEntryUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    is_recurring: Optional[bool] = None
    is_paid: Optional[bool] = None
    is_credit_card: Optional[bool] = None
    frequency: Optional[str] = None
    day_of_month: Optional[int] = Field(None, ge=1, le=31)
    notes: Optional[str] = None


class BudgetAccountCreate(BaseModel):
    name: str
    purpose: str = ""  # What the account is for
    balance: float = 0.0
    payment_date: Optional[int] = None  # Day of month
    notes: str = ""
    sort_order: int = 0


class BudgetAccountUpdate(BaseModel):
    name: Optional[str] = None
    purpose: Optional[str] = None
    balance: Optional[float] = None
    payment_date: Optional[int] = None
    notes: Optional[str] = None
    sort_order: Optional[int] = None


class BudgetLoanCreate(BaseModel):
    bank: str
    purpose: str = ""  # What the loan is for
    original_debt: float = 0.0
    remaining_debt: float
    credit_limit: float = 0.0  # Credit limit (for credit lines)
    monthly_payment: float
    payment_date: Optional[int] = None  # Day of month
    notes: str = ""
    sort_order: int = 0


class BudgetLoanUpdate(BaseModel):
    bank: Optional[str] = None
    purpose: Optional[str] = None
    original_debt: Optional[float] = None
    remaining_debt: Optional[float] = None
    credit_limit: Optional[float] = None
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
    items = await db[ENTRIES_COL].find(query, {"_id": 0}).sort([("frequency", 1), ("day_of_month", 1), ("sort_order", 1)]).to_list(1000)
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
        "is_credit_card": body.is_credit_card,
        "frequency": body.frequency,
        "month_key": mk,
        "day_of_month": body.day_of_month if body.frequency != "daily" else None,
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
    updates = body.model_dump(exclude_unset=True)
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


# ── Daily Group Operations ──────────────────────────────────────────

@router.delete("/entries/daily-group/{group_id}")
async def delete_daily_group(
    group_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete all entries in a daily group."""
    result = await db[ENTRIES_COL].delete_many({"daily_group": group_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Daily group not found")
    return {"ok": True, "deleted": result.deleted_count}


@router.patch("/entries/daily-group/{group_id}")
async def update_daily_group(
    group_id: str,
    body: BudgetEntryUpdate,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update shared fields for all entries in a daily group."""
    updates = body.model_dump(exclude_unset=True)
    group_fields = {}
    for k in ("name", "category", "notes", "is_recurring", "is_credit_card", "frequency"):
        if k in updates:
            group_fields[k] = updates[k]
    if not group_fields:
        raise HTTPException(400, "No group-level fields to update")
    group_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db[ENTRIES_COL].update_many(
        {"daily_group": group_id},
        {"$set": group_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Daily group not found")
    return {"ok": True, "updated": result.matched_count}


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

    import calendar as cal_mod
    t_year, t_month = map(int, target_month.split("-"))
    t_days = cal_mod.monthrange(t_year, t_month)[1]

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

    if not new_entries:
        return {"message": "No entries to create", "created": 0}
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
    available_cash: float = Query(0.0, description="Current available cash on hand"),
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

    import calendar as cal_mod
    year, month = map(int, mk.split("-"))
    days_in_month = cal_mod.monthrange(year, month)[1]

    total_income = 0.0
    total_expense = 0.0
    income_paid = 0.0
    expense_paid = 0.0
    income_by_cat: dict[str, float] = {}
    expense_by_cat: dict[str, float] = {}
    # Forward-looking unpaid: only future obligations
    unpaid_expense_forward = 0.0

    # Remaining days in month
    today = date.today()
    if year == today.year and month == today.month:
        remaining_days = max(days_in_month - today.day + 1, 1)
    else:
        remaining_days = days_in_month  # past/future month: show full

    for e in entries:
        base_amt = e.get("amount", 0)
        freq = e.get("frequency", "once")
        if freq == "daily":
            amt = base_amt * days_in_month
        elif freq == "weekly":
            start_day = e.get("day_of_month") or 1
            occurrences = len(range(start_day, days_in_month + 1, 7))
            amt = base_amt * occurrences
        else:
            amt = base_amt
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
            else:
                # Calculate forward-looking unpaid amount
                if freq == "daily":
                    unpaid_expense_forward += base_amt * remaining_days
                elif freq == "weekly":
                    start_day = e.get("day_of_month") or 1
                    future_start = max(start_day, today.day) if year == today.year and month == today.month else start_day
                    future_occ = len(range(future_start, days_in_month + 1, 7))
                    unpaid_expense_forward += base_amt * future_occ
                else:
                    unpaid_expense_forward += base_amt
            expense_by_cat[cat] = expense_by_cat.get(cat, 0) + amt

    balance = total_income - total_expense

    # Loan payments for this month
    loans = await db[LOANS_COL].find({}, {"_id": 0}).to_list(100)
    total_loan_payments = sum(l.get("monthly_payment", 0) for l in loans)
    loan_paid = 0.0
    for l in loans:
        paid_months = l.get("paid_months", [])
        if mk in paid_months:
            loan_paid += l.get("monthly_payment", 0)

    # Include loans in totals for accurate balance
    total_expense_with_loans = total_expense + total_loan_payments
    expense_paid_with_loans = expense_paid + loan_paid
    balance_with_loans = total_income - total_expense_with_loans

    # Forward-looking unpaid: only future obligations
    # unpaid_expense_forward already has remaining daily/weekly + all unpaid one-time expenses
    # Add unpaid loan payments
    unpaid_forward_with_loans = unpaid_expense_forward + (total_loan_payments - loan_paid)
    still_needed = max(unpaid_forward_with_loans - available_cash, 0)
    min_daily = still_needed / remaining_days if remaining_days > 0 else 0

    return {
        "month_key": mk,
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense_with_loans, 2),
        "balance": round(balance_with_loans, 2),
        "income_paid": round(income_paid, 2),
        "expense_paid": round(expense_paid_with_loans, 2),
        "unpaid_expense": round(unpaid_forward_with_loans, 2),
        "income_by_category": {k: round(v, 2) for k, v in sorted(income_by_cat.items())},
        "expense_by_category": {k: round(v, 2) for k, v in sorted(expense_by_cat.items())},
        "remaining_days": remaining_days,
        "min_daily_earnings": round(min_daily, 2),
        "total_loan_payments": round(total_loan_payments, 2),
        "available_cash": round(available_cash, 2),
        "entries_expense": round(total_expense, 2),
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
    items = await db[LOANS_COL].find({}, {"_id": 0}).sort([("payment_date", 1), ("sort_order", 1)]).to_list(100)
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


@router.patch("/loans/{loan_id}/toggle-paid")
async def toggle_loan_paid(
    loan_id: str,
    month_key: Optional[str] = Query(None, description="YYYY-MM"),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Toggle loan payment paid status for a specific month."""
    mk = month_key or _current_month_key()
    doc = await db[LOANS_COL].find_one({"id": loan_id})
    if not doc:
        raise HTTPException(404, "Loan not found")
    paid_months = doc.get("paid_months", [])
    if mk in paid_months:
        paid_months.remove(mk)
        is_paid = False
    else:
        paid_months.append(mk)
        is_paid = True
    await db[LOANS_COL].update_one(
        {"id": loan_id},
        {"$set": {"paid_months": paid_months, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"id": loan_id, "month_key": mk, "is_paid": is_paid}


# ── Agent-Readable Summary ──────────────────────────────────────────

@router.get("/calendar")
async def get_calendar(
    month_key: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """
    Get calendar data for a month: all entries and loan payments organized by day,
    with running balance calculation.
    """
    import calendar as cal

    mk = month_key or _current_month_key()
    year, month = map(int, mk.split("-"))
    days_in_month = cal.monthrange(year, month)[1]

    entries = await db[ENTRIES_COL].find(
        {"month_key": mk}, {"_id": 0}
    ).to_list(1000)
    loans = await db[LOANS_COL].find({}, {"_id": 0}).to_list(100)
    accounts = await db[ACCOUNTS_COL].find({}, {"_id": 0}).to_list(100)

    # Starting balance = sum of all account balances
    starting_balance = sum(a.get("balance", 0) for a in accounts)

    # Build day map: {day: [events]}
    day_map: dict[int, list] = {d: [] for d in range(1, days_in_month + 1)}
    # Unscheduled items (no day_of_month)
    unscheduled = []

    for e in entries:
        freq = e.get("frequency", "once")
        day = e.get("day_of_month")
        item = {
            "id": e.get("id"),
            "name": e.get("name", ""),
            "amount": e.get("amount", 0),
            "type": e.get("type", "expense"),
            "category": e.get("category", ""),
            "is_paid": e.get("is_paid", False),
            "is_recurring": e.get("is_recurring", False),
            "frequency": freq,
            "source": "entry",
        }
        if freq == "daily":
            # Place on every day of the month
            for d in range(1, days_in_month + 1):
                day_map[d].append({**item})
        elif freq == "weekly":
            # Place every 7 days starting from day_of_month
            start = day or 1
            for d in range(start, days_in_month + 1, 7):
                day_map[d].append({**item})
        else:
            if day and 1 <= day <= days_in_month:
                day_map[day].append(item)
            else:
                unscheduled.append(item)

    # Auto-add loan payments to calendar
    for loan in loans:
        day = loan.get("payment_date")
        paid_months = loan.get("paid_months", [])
        item = {
            "id": f"loan_{loan.get('id', '')}",
            "name": f"Loan: {loan.get('bank', '')}",
            "amount": loan.get("monthly_payment", 0),
            "type": "expense",
            "category": "Loan Payment",
            "is_paid": mk in paid_months,
            "is_recurring": True,
            "source": "loan",
            "purpose": loan.get("purpose", ""),
        }
        if day and 1 <= day <= days_in_month:
            day_map[day].append(item)
        else:
            unscheduled.append(item)

    # Calculate running balance per day
    running = starting_balance
    # First, subtract unscheduled expenses and add unscheduled income
    # (treat them as already applied to balance)
    calendar_days = []
    # Compute daily projected balance
    running = starting_balance
    for d in range(1, days_in_month + 1):
        day_income = sum(i["amount"] for i in day_map[d] if i["type"] == "income")
        day_expense = sum(i["amount"] for i in day_map[d] if i["type"] == "expense")
        running = running + day_income - day_expense
        calendar_days.append({
            "day": d,
            "items": day_map[d],
            "income": round(day_income, 2),
            "expense": round(day_expense, 2),
            "balance": round(running, 2),
        })

    return {
        "month_key": mk,
        "year": year,
        "month": month,
        "days_in_month": days_in_month,
        "first_weekday": cal.monthrange(year, month)[0],  # 0=Mon, 6=Sun
        "starting_balance": round(starting_balance, 2),
        "days": calendar_days,
        "unscheduled": unscheduled,
    }


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
            freq = e.get("frequency", "once")
            if freq == "daily":
                rec = "daily"
            elif freq == "weekly":
                rec = "weekly"
            else:
                rec = "recurring" if e.get("is_recurring") else "one-time"
            day = f" (day {e['day_of_month']})" if e.get("day_of_month") else ""
            freq_tag = f" [{freq.upper()}]" if freq != "once" else ""
            lines.append(f"  [{paid}] {e['name']}: ${e['amount']:,.2f} ({e.get('category', '')}, {rec}){day}{freq_tag}")

    # Expense breakdown
    expense_entries = [e for e in entries if e.get("type") == "expense"]
    if expense_entries:
        lines.append("--- Expenses ---")
        for e in expense_entries:
            paid = "PAID" if e.get("is_paid") else "UNPAID"
            freq = e.get("frequency", "once")
            if freq == "daily":
                rec = "daily"
            elif freq == "weekly":
                rec = "weekly"
            else:
                rec = "recurring" if e.get("is_recurring") else "one-time"
            day = f" (day {e['day_of_month']})" if e.get("day_of_month") else ""
            freq_tag = f" [{freq.upper()}]" if freq != "once" else ""
            lines.append(f"  [{paid}] {e['name']}: ${e['amount']:,.2f} ({e.get('category', '')}, {rec}){day}{freq_tag}")

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
            pd = f" (payment day: {a['payment_date']})" if a.get("payment_date") else ""
            purpose = f" — {a['purpose']}" if a.get("purpose") else ""
            lines.append(f"  {a['name']}: ${a.get('balance', 0):,.2f}{pd}{purpose}")

    # Loans
    if loans:
        lines.append("")
        lines.append("--- Loans ---")
        for l in loans:
            pd = f" (payment day: {l['payment_date']})" if l.get("payment_date") else ""
            purpose = f" — {l['purpose']}" if l.get("purpose") else ""
            limit_str = f", limit ${l['credit_limit']:,.2f}" if l.get("credit_limit") else ""
            mp = l.get("monthly_payment", 0)
            remaining_payments = f", ~{int(l['remaining_debt'] / mp)} payments left" if mp > 0 else ""
            lines.append(f"  {l['bank']}: debt ${l.get('remaining_debt', 0):,.2f}, monthly ${mp:,.2f}{limit_str}{remaining_payments}{pd}{purpose}")

    return {"summary": "\n".join(lines)}
