
# Personal Finance Management Application
"""
Personal Finance Management Application (CLI)
=================================================
Features (per guidelines):
- User Registration & Authentication (username + salted password hash)
- Income & Expense Tracking (add, list, update, delete; categories, notes, dates)
- Financial Reports (monthly/yearly totals: income, expense, savings)
- Budgeting (set monthly category budgets, warn when exceeded)
- Data Persistence (SQLite)
- Backup & Restore (copy/replace DB file)
- Error handling & user-friendly CLI
- Unit Tests (run with: python app.py --test)

How to run:
  python app.py                # interactive CLI
  python app.py --db pfm.db    # use a custom DB file
  python app.py --test         # run unit tests

Standard-library only. No external dependencies required.
"""
from __future__ import annotations
import argparse
import calendar
import datetime as dt
import getpass
import hmac
import hashlib
import os
import shutil
import sqlite3
import sys
import textwrap
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict

# ----------------------------- Constants ------------------------------------
DEFAULT_DB_PATH = os.environ.get("PFM_DB", "pfm.sqlite3")
DATE_FMT = "%Y-%m-%d"  # ISO format
MONTH_FMT = "%Y-%m"    # e.g., 2025-09

# ----------------------------- Utilities ------------------------------------

def hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """Return (salt, hash) using PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt, pwd_hash


def verify_password(password: str, salt: bytes, pwd_hash: bytes) -> bool:
    _salt, new_hash = hash_password(password, salt)
    return hmac.compare_digest(pwd_hash, new_hash)


def input_date(prompt: str, default: Optional[str] = None) -> str:
    while True:
        raw = input(f"{prompt} [{default or 'YYYY-MM-DD'}]: ").strip() or (default or "")
        try:
            if not raw:
                raise ValueError
            dt.datetime.strptime(raw, DATE_FMT)
            return raw
        except ValueError:
            print("  ! Please enter a valid date in YYYY-MM-DD format.")


def input_float(prompt: str, min_value: Optional[float] = None) -> float:
    while True:
        raw = input(prompt).strip()
        try:
            val = float(raw)
            if min_value is not None and val < min_value:
                print(f"  ! Value must be >= {min_value}")
                continue
            return val
        except ValueError:
            print("  ! Please enter a valid number.")


def pause(msg: str = "Press Enter to continue..."):
    input(msg)

# ----------------------------- Database Layer -------------------------------

class Database:
    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ttype TEXT NOT NULL CHECK(ttype IN ('income','expense')),
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0),
                tdate TEXT NOT NULL,  -- YYYY-MM-DD
                note TEXT
            );

            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                month TEXT NOT NULL,  -- YYYY-MM
                monthly_limit REAL NOT NULL CHECK(monthly_limit >= 0),
                UNIQUE(user_id, category, month)
            );
            """
        )
        self.conn.commit()

    # ------------------------- Users -------------------------
    def create_user(self, username: str, password: str) -> int:
        salt, pwd_hash = hash_password(password)
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO users(username, salt, password_hash, created_at) VALUES(?,?,?,?)",
            (username, salt, pwd_hash, dt.datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_user(self, username: str) -> Optional[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()

    # ---------------------- Transactions ----------------------
    def add_transaction(self, user_id: int, ttype: str, category: str, amount: float, tdate: str, note: str = "") -> int:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO transactions(user_id, ttype, category, amount, tdate, note)
            VALUES(?,?,?,?,?,?)
            """,
            (user_id, ttype, category, amount, tdate, note),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_transaction(self, tid: int, user_id: int, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [tid, user_id]
        cur = self.conn.cursor()
        cur.execute(f"UPDATE transactions SET {cols} WHERE id = ? AND user_id = ?", vals)
        self.conn.commit()

    def delete_transaction(self, tid: int, user_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (tid, user_id))
        self.conn.commit()

    def list_transactions(self, user_id: int, month: Optional[str] = None) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        if month:
            cur.execute(
                "SELECT * FROM transactions WHERE user_id = ? AND substr(tdate,1,7) = ? ORDER BY tdate DESC, id DESC",
                (user_id, month),
            )
        else:
            cur.execute(
                "SELECT * FROM transactions WHERE user_id = ? ORDER BY tdate DESC, id DESC",
                (user_id,),
            )
        return cur.fetchall()

    def month_totals(self, user_id: int, month: str) -> Dict[str, float]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT ttype, COALESCE(SUM(amount),0) as total
            FROM transactions
            WHERE user_id = ? AND substr(tdate,1,7) = ?
            GROUP BY ttype
            """,
            (user_id, month),
        )
        data = {"income": 0.0, "expense": 0.0}
        for row in cur.fetchall():
            data[row[0]] = float(row[1])
        return data

    def year_totals(self, user_id: int, year: int) -> Dict[str, float]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT ttype, COALESCE(SUM(amount),0) as total
            FROM transactions
            WHERE user_id = ? AND substr(tdate,1,4) = ?
            GROUP BY ttype
            """,
            (user_id, str(year)),
        )
        data = {"income": 0.0, "expense": 0.0}
        for row in cur.fetchall():
            data[row[0]] = float(row[1])
        return data

    def category_month_expense(self, user_id: int, category: str, month: str) -> float:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM transactions
            WHERE user_id = ? AND ttype='expense' AND category = ? AND substr(tdate,1,7) = ?
            """,
            (user_id, category, month),
        )
        return float(cur.fetchone()[0])

    # ------------------------- Budgets ------------------------
    def set_budget(self, user_id: int, category: str, month: str, monthly_limit: float) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO budgets(user_id, category, month, monthly_limit)
            VALUES(?,?,?,?)
            ON CONFLICT(user_id, category, month)
            DO UPDATE SET monthly_limit = excluded.monthly_limit
            """,
            (user_id, category, month, monthly_limit),
        )
        self.conn.commit()

    def get_budget(self, user_id: int, category: str, month: str) -> Optional[float]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT monthly_limit FROM budgets WHERE user_id = ? AND category = ? AND month = ?",
            (user_id, category, month),
        )
        row = cur.fetchone()
        return float(row[0]) if row else None

    def list_budgets(self, user_id: int, month: Optional[str] = None) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        if month:
            cur.execute("SELECT * FROM budgets WHERE user_id = ? AND month = ? ORDER BY category", (user_id, month))
        else:
            cur.execute("SELECT * FROM budgets WHERE user_id = ? ORDER BY month DESC, category", (user_id,))
        return cur.fetchall()

# ----------------------------- Services -------------------------------------

class AuthService:
    def __init__(self, db: Database):
        self.db = db

    def register(self, username: str, password: str) -> int:
        if self.db.get_user(username):
            raise ValueError("Username already exists.")
        return self.db.create_user(username, password)

    def login(self, username: str, password: str) -> Optional[int]:
        row = self.db.get_user(username)
        if not row:
            return None
        if verify_password(password, row["salt"], row["password_hash"]):
            return int(row["id"]) 
        return None


class BudgetService:
    def __init__(self, db: Database):
        self.db = db

    def set_budget(self, user_id: int, category: str, month: str, limit_amt: float):
        self.db.set_budget(user_id, category, month, limit_amt)

    def check_and_warn(self, user_id: int, category: str, month: str) -> Optional[str]:
        limit = self.db.get_budget(user_id, category, month)
        if limit is None:
            return None
        spent = self.db.category_month_expense(user_id, category, month)
        if spent > limit:
            return f"WARNING: Budget exceeded for '{category}' in {month}: spent {spent:.2f} > limit {limit:.2f}."
        elif spent > 0.9 * limit:
            return f"ALERT: You are close to exceeding the '{category}' budget in {month}: {spent:.2f}/{limit:.2f}."
        return None


class ReportService:
    def __init__(self, db: Database):
        self.db = db

    def monthly_report(self, user_id: int, month: str) -> Dict[str, float]:
        totals = self.db.month_totals(user_id, month)
        savings = totals["income"] - totals["expense"]
        return {**totals, "savings": savings}

    def yearly_report(self, user_id: int, year: int) -> Dict[str, float]:
        totals = self.db.year_totals(user_id, year)
        savings = totals["income"] - totals["expense"]
        return {**totals, "savings": savings}


class BackupService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def backup(self, dest_dir: str) -> str:
        os.makedirs(dest_dir, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(dest_dir, f"pfm-backup-{ts}.sqlite3")
        shutil.copy2(self.db_path, dest)
        return dest

    def restore(self, backup_path: str) -> None:
        if not os.path.isfile(backup_path):
            raise FileNotFoundError("Backup file not found")
        shutil.copy2(backup_path, self.db_path)

# ----------------------------- CLI ------------------------------------------

class CLI:
    def __init__(self, db: Database):
        self.db = db
        self.auth = AuthService(db)
        self.budgets = BudgetService(db)
        self.reports = ReportService(db)
        self.backup = BackupService(db.path)
        self.user_id: Optional[int] = None
        self.username: Optional[str] = None

    # ---- Entry ----
    def start(self):
        self._welcome()
        while True:
            if not self.user_id:
                choice = self._menu_auth()
                if choice == "1":
                    self._handle_register()
                elif choice == "2":
                    self._handle_login()
                elif choice == "3":
                    print("Goodbye!")
                    break
            else:
                choice = self._menu_main()
                if choice == "1":
                    self._menu_transactions()
                elif choice == "2":
                    self._menu_budgets()
                elif choice == "3":
                    self._menu_reports()
                elif choice == "4":
                    self._menu_backup_restore()
                elif choice == "5":
                    print(f"User '{self.username}' logged out.")
                    self.user_id = None
                    self.username = None
                elif choice == "6":
                    print("Goodbye!")
                    break

    def _welcome(self):
        print("\nPersonal Finance Manager\n" + "-" * 27)

    def _menu_auth(self) -> str:
        print("\n1) Register\n2) Login\n3) Exit")
        return input("Select: ").strip()

    def _menu_main(self) -> str:
        print(
            textwrap.dedent(
                f"""
                \nLogged in as: {self.username}
                ---------------------------
                1) Transactions (add/list/update/delete)
                2) Budgets (set/list)
                3) Reports (monthly/yearly)
                4) Backup & Restore
                5) Logout
                6) Exit
                """
            )
        )
        return input("Select: ").strip()

    # ---- Auth Handlers ----
    def _handle_register(self):
        print("\n== Register ==")
        username = input("Username: ").strip()
        if not username:
            print("  ! Username required.")
            return
        pwd = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm: ")
        if pwd != confirm:
            print("  ! Passwords do not match.")
            return
        try:
            uid = self.auth.register(username, pwd)
            print(f"  ✓ Registered user '{username}' (id={uid})")
        except ValueError as e:
            print(f"  ! {e}")

    def _handle_login(self):
        print("\n== Login ==")
        username = input("Username: ").strip()
        pwd = getpass.getpass("Password: ")
        uid = self.auth.login(username, pwd)
        if uid:
            self.user_id = uid
            self.username = username
            print(f"  ✓ Welcome, {username}!")
        else:
            print("  ! Invalid credentials.")

    # ---- Transactions ----
    def _menu_transactions(self):
        while True:
            print("\nTransactions:\n1) Add\n2) List\n3) Update\n4) Delete\n5) Back")
            choice = input("Select: ").strip()
            if choice == "1":
                self._tx_add()
            elif choice == "2":
                self._tx_list()
            elif choice == "3":
                self._tx_update()
            elif choice == "4":
                self._tx_delete()
            elif choice == "5":
                break

    def _tx_add(self):
        print("\n== Add Transaction ==")
        ttype = input("Type ('income' or 'expense'): ").strip().lower()
        if ttype not in ("income", "expense"):
            print("  ! Invalid type.")
            return
        category = input("Category (e.g., Salary, Rent, Food): ").strip()
        amount = input_float("Amount: ", min_value=0.0)
        today = dt.date.today().strftime(DATE_FMT)
        tdate = input_date("Date", default=today)
        note = input("Note (optional): ").strip()
        tid = self.db.add_transaction(self.user_id, ttype, category, amount, tdate, note)
        print(f"  ✓ Added transaction id={tid}.")

        # Budget warning if expense
        if ttype == "expense":
            month = tdate[:7]
            warn = self.budgets.check_and_warn(self.user_id, category, month)
            if warn:
                print("  " + warn)

    def _tx_list(self):
        print("\n== List Transactions ==")
        month = input(f"Month filter (YYYY-MM) or Enter for all: ").strip() or None
        rows = self.db.list_transactions(self.user_id, month)
        if not rows:
            print("  (no transactions)")
            return
        print(f"  Showing {len(rows)} transactions:")
        for r in rows:
            print(f"  [{r['id']}] {r['tdate']} {r['ttype'].upper():7} {r['category']:<12} ${r['amount']:>8.2f} :: {r['note'] or ''}")

    def _tx_update(self):
        print("\n== Update Transaction ==")
        tid = int(input("Transaction ID: ").strip())
        fields = {}
        if input("Change type? (y/N): ").strip().lower() == 'y':
            ttype = input("  New type ('income'/'expense'): ").strip().lower()
            if ttype in ("income", "expense"):
                fields['ttype'] = ttype
        if input("Change category? (y/N): ").strip().lower() == 'y':
            fields['category'] = input("  New category: ").strip()
        if input("Change amount? (y/N): ").strip().lower() == 'y':
            fields['amount'] = input_float("  New amount: ", min_value=0.0)
        if input("Change date? (y/N): ").strip().lower() == 'y':
            fields['tdate'] = input_date("  New date")
        if input("Change note? (y/N): ").strip().lower() == 'y':
            fields['note'] = input("  New note: ").strip()
        if fields:
            self.db.update_transaction(tid, self.user_id, **fields)
            print("  ✓ Updated.")
        else:
            print("  (no changes)")

    def _tx_delete(self):
        print("\n== Delete Transaction ==")
        tid = int(input("Transaction ID: ").strip())
        self.db.delete_transaction(tid, self.user_id)
        print("  ✓ Deleted.")

    # ---- Budgets ----
    def _menu_budgets(self):
        while True:
            print("\nBudgets:\n1) Set/Update Monthly Budget\n2) List Budgets\n3) Back")
            choice = input("Select: ").strip()
            if choice == "1":
                self._budget_set()
            elif choice == "2":
                self._budget_list()
            elif choice == "3":
                break

    def _budget_set(self):
        print("\n== Set/Update Budget ==")
        category = input("Category (e.g., Food, Rent): ").strip()
        today_month = dt.date.today().strftime(MONTH_FMT)
        month = input(f"Month (YYYY-MM) [{today_month}]: ").strip() or today_month
        # validate month
        try:
            dt.datetime.strptime(month, MONTH_FMT)
        except ValueError:
            print("  ! Invalid month format.")
            return
        limit_amt = input_float("Monthly limit: ", min_value=0.0)
        self.budgets.set_budget(self.user_id, category, month, limit_amt)
        print("  ✓ Budget saved.")

    def _budget_list(self):
        print("\n== List Budgets ==")
        month = input("Month filter (YYYY-MM) or Enter for all: ").strip() or None
        if month:
            try:
                dt.datetime.strptime(month, MONTH_FMT)
            except ValueError:
                print("  ! Invalid month format.")
                return
        rows = self.db.list_budgets(self.user_id, month)
        if not rows:
            print("  (no budgets)")
            return
        for r in rows:
            spent = self.db.category_month_expense(self.user_id, r['category'], r['month'])
            print(f"  {r['month']} | {r['category']:<12} limit ${r['monthly_limit']:>8.2f} | spent ${spent:>8.2f}")

    # ---- Reports ----
    def _menu_reports(self):
        while True:
            print("\nReports:\n1) Monthly\n2) Yearly\n3) Back")
            choice = input("Select: ").strip()
            if choice == "1":
                self._report_monthly()
            elif choice == "2":
                self._report_yearly()
            elif choice == "3":
                break

    def _report_monthly(self):
        today_month = dt.date.today().strftime(MONTH_FMT)
        month = input(f"Month (YYYY-MM) [{today_month}]: ").strip() or today_month
        try:
            dt.datetime.strptime(month, MONTH_FMT)
        except ValueError:
            print("  ! Invalid month format.")
            return
        totals = self.reports.monthly_report(self.user_id, month)
        print(f"\n== Monthly Report: {month} ==")
        print(f"  Income : ${totals['income']:.2f}")
        print(f"  Expense: ${totals['expense']:.2f}")
        print(f"  Savings: ${totals['savings']:.2f}")

    def _report_yearly(self):
        year = input(f"Year (YYYY) [{dt.date.today().year}]: ").strip() or str(dt.date.today().year)
        if not (year.isdigit() and len(year) == 4):
            print("  ! Invalid year.")
            return
        totals = self.reports.yearly_report(self.user_id, int(year))
        print(f"\n== Yearly Report: {year} ==")
        print(f"  Income : ${totals['income']:.2f}")
        print(f"  Expense: ${totals['expense']:.2f}")
        print(f"  Savings: ${totals['savings']:.2f}")

    # ---- Backup / Restore ----
    def _menu_backup_restore(self):
        while True:
            print("\nBackup/Restore:\n1) Backup DB\n2) Restore DB\n3) Back")
            choice = input("Select: ").strip()
            if choice == "1":
                dest = input("Destination folder (will be created if missing): ").strip() or "backups"
                path = self.backup.backup(dest)
                print(f"  ✓ Backup saved to: {path}")
            elif choice == "2":
                backup_path = input("Path to backup file: ").strip()
                try:
                    self.backup.restore(backup_path)
                    print("  ✓ Restore complete. Please restart the app.")
                except Exception as e:
                    print(f"  ! Restore failed: {e}")
            elif choice == "3":
                break

# ----------------------------- Tests ----------------------------------------

def run_tests():
    import unittest
    class PFMBasicTests(unittest.TestCase):
        def setUp(self):
            self.tmp_db = Database(":memory:")
            self.cli = CLI(self.tmp_db)
            # Create a user and login
            self.username = "alice"
            self.password = "secret123"
            uid = self.cli.auth.register(self.username, self.password)
            self.user_id = uid

        def test_login_success(self):
            uid = self.cli.auth.login(self.username, self.password)
            self.assertIsNotNone(uid)

        def test_add_income_expense_and_reports(self):
            # Add income
            today = dt.date.today().strftime(DATE_FMT)
            self.tmp_db.add_transaction(self.user_id, 'income', 'Salary', 3000.0, today, 'Monthly salary')
            # Add expense
            self.tmp_db.add_transaction(self.user_id, 'expense', 'Food', 200.0, today, 'Groceries')
            month = today[:7]
            rep = self.cli.reports.monthly_report(self.user_id, month)
            self.assertAlmostEqual(rep['income'], 3000.0)
            self.assertAlmostEqual(rep['expense'], 200.0)
            self.assertAlmostEqual(rep['savings'], 2800.0)

        def test_budget_alert(self):
            today = dt.date.today().strftime(DATE_FMT)
            month = today[:7]
            self.tmp_db.set_budget(self.user_id, 'Food', month, 100.0)
            # Spend over budget
            self.tmp_db.add_transaction(self.user_id, 'expense', 'Food', 120.0, today, 'Dinner')
            msg = self.cli.budgets.check_and_warn(self.user_id, 'Food', month)
            self.assertIsNotNone(msg)
            self.assertIn('Budget exceeded', msg)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PFMBasicTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1

# ----------------------------- Main -----------------------------------------

def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description="Personal Finance Manager (CLI)")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Path to SQLite DB file")
    parser.add_argument("--test", action="store_true", help="Run unit tests and exit")
    args = parser.parse_args(argv)

    if args.test:
        code = run_tests()
        sys.exit(code)

    db = Database(args.db)
    cli = CLI(db)
    try:
        cli.start()
    finally:
        db.conn.close()

if __name__ == "__main__":
    main()
