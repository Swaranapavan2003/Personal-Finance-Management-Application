# Personal-Finance-Management-Application

Personal Finance Manager (CLI)

A Personal Finance Management Application built in Python.
This app helps users track income and expenses, set budgets, generate reports, and back up data — all from the command line.

# Features

* User Authentication – Register & login with securely hashed passwords (PBKDF2 + salt).
* Income & Expense Tracking – Add, update, delete, and list transactions with categories, notes, and dates.
* Budgeting – Set monthly budgets per category, with warnings when spending exceeds limits.
* Reports – Generate monthly & yearly summaries (income, expenses, savings).
* Backup & Restore – Create timestamped database backups, restore when needed.
* SQLite Persistence – All data stored locally in an SQLite3 database.
* Error Handling – User-friendly prompts & validation.
* Unit Tests – Basic automated tests to verify functionality.

# Tech Stack

* Python 3.8+ (Standard Library only – no external dependencies required)
* SQLite3 for data persistence
* Hashlib (PBKDF2) for secure password hashing
* Argparse for CLI arguments
* Unittest for testing

# Installation & Setup

* Clone or download this repository:
* https://github.com/Swaranapavan2003/Personal-Finance-Management-Application.git

* Run the application:
* python app.py

* To run tests:
* python app.py --test

# Usage Guide
* User Authentication
* Register with a username + password.
* Login with your credentials.
* Passwords are stored securely using salted PBKDF2 hashing.

 # Transactions
 * Add income or expense entries.
 * Record details: category (e.g., Food, Rent), amount, date, and notes.
 * Update or delete past transactions.
 * List transactions by month or view all.

 # Reports
 * Monthly Report: Shows total income, expenses, and savings.
 * Yearly Report: Summarizes yearly totals.

 # Budgets
  * Set category-specific monthly budgets (e.g., limit “Food” to $300).
  * Alerts:
  * Close to exceeding budget (90%+ used).
  * Budget exceeded.

  # Backup & Restore
  * Backup: Creates a timestamped SQLite file in a chosen folder.
  * Restore: Replace current database with a backup file.

  # Testing
  * Run built-in unit tests:
  * python app.py --test

  # Tests cover:
  * User authentication
  * Adding income & expenses
  * Monthly reports
  * Budget alerts


  # Security Notes
  * Passwords are never stored in plain text.
  * Uses PBKDF2-HMAC-SHA256 with 200,000 iterations for password hashing.
  * SQLite database is local; backup regularly to avoid data loss



