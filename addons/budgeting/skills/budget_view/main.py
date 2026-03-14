from datetime import datetime, timezone, date
import calendar


async def execute(month_key: str = ""):
    """Get budget summary for a month."""
    from app.database import get_mongodb

    if not month_key:
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        db = get_mongodb()

        entries = await db["budget_entries"].find(
            {"month_key": month_key}, {"_id": 0}
        ).to_list(1000)
        accounts = await db["budget_accounts"].find({}, {"_id": 0}).to_list(100)
        loans = await db["budget_loans"].find({}, {"_id": 0}).to_list(100)

        total_income = 0.0
        total_expense = 0.0
        income_paid = 0.0
        expense_paid = 0.0

        for e in entries:
            amt = e.get("amount", 0)
            if e.get("type") == "income":
                total_income += amt
                if e.get("is_paid"):
                    income_paid += amt
            else:
                total_expense += amt
                if e.get("is_paid"):
                    expense_paid += amt

        balance = total_income - total_expense
        year, month = map(int, month_key.split("-"))
        today = date.today()
        if year == today.year and month == today.month:
            days_in_month = calendar.monthrange(year, month)[1]
            remaining_days = max(days_in_month - today.day + 1, 1)
        else:
            remaining_days = 1

        unpaid_expenses = total_expense - expense_paid
        remaining_needed = max(unpaid_expenses - (income_paid - expense_paid), 0)
        min_daily = remaining_needed / remaining_days if remaining_days > 0 else 0

        lines = [f"=== Budget Summary for {month_key} ==="]
        lines.append(f"Total Income: ${total_income:,.2f} (received: ${income_paid:,.2f})")
        lines.append(f"Total Expenses: ${total_expense:,.2f} (paid: ${expense_paid:,.2f})")
        lines.append(f"Balance: ${balance:,.2f}")
        lines.append(f"Min Daily Earnings Needed: ${min_daily:,.2f}")
        lines.append(f"Remaining Days: {remaining_days}")
        lines.append("")

        income_entries = [e for e in entries if e.get("type") == "income"]
        if income_entries:
            lines.append("--- Income ---")
            for e in income_entries:
                paid = "PAID" if e.get("is_paid") else "UNPAID"
                rec = "recurring" if e.get("is_recurring") else "one-time"
                lines.append(f"  [{paid}] {e['name']}: ${e['amount']:,.2f} ({e.get('category', '')}, {rec})")

        expense_entries = [e for e in entries if e.get("type") == "expense"]
        if expense_entries:
            lines.append("--- Expenses ---")
            for e in expense_entries:
                paid = "PAID" if e.get("is_paid") else "UNPAID"
                rec = "recurring" if e.get("is_recurring") else "one-time"
                lines.append(f"  [{paid}] {e['name']}: ${e['amount']:,.2f} ({e.get('category', '')}, {rec})")

        if accounts:
            lines.append("")
            lines.append("--- Accounts ---")
            for a in accounts:
                cc = " [Credit Card]" if a.get("is_credit_card") else ""
                pd = f" (payment day: {a['payment_date']})" if a.get("payment_date") else ""
                lines.append(f"  {a['name']}: ${a.get('balance', 0):,.2f}{cc}{pd}")

        if loans:
            lines.append("")
            lines.append("--- Loans ---")
            for l in loans:
                pd = f" (payment day: {l['payment_date']})" if l.get("payment_date") else ""
                lines.append(f"  {l['bank']}: debt ${l.get('remaining_debt', 0):,.2f}, monthly ${l.get('monthly_payment', 0):,.2f}{pd}")

        return {"summary": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Failed to fetch budget summary: {e}"}
