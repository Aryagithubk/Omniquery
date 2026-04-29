"""
create_demo_db.py — Creates a sample SQLite database for the DBAgent demo.
Run this script once to populate data/demo.db.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "demo.db")


def create_demo_database():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── Departments ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            budget REAL DEFAULT 0,
            manager TEXT
        )
    """)
    departments = [
        ("Engineering", 500000, "Alice Johnson"),
        ("Marketing", 250000, "Bob Smith"),
        ("Sales", 350000, "Charlie Brown"),
        ("Human Resources", 150000, "Diana Prince"),
        ("Finance", 200000, "Edward Norton"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO departments (name, budget, manager) VALUES (?, ?, ?)",
        departments,
    )

    # ── Employees ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            department TEXT NOT NULL,
            position TEXT NOT NULL,
            salary REAL NOT NULL,
            hire_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)
    employees = [
        ("Alice Johnson", "alice@company.com", "Engineering", "VP of Engineering", 180000, "2020-01-15", 1),
        ("Bob Smith", "bob@company.com", "Marketing", "Marketing Director", 140000, "2019-06-01", 1),
        ("Charlie Brown", "charlie@company.com", "Sales", "Sales Manager", 120000, "2021-03-10", 1),
        ("Diana Prince", "diana@company.com", "Human Resources", "HR Director", 130000, "2018-11-20", 1),
        ("Edward Norton", "edward@company.com", "Finance", "CFO", 160000, "2017-08-05", 1),
        ("Frank Castle", "frank@company.com", "Engineering", "Senior Developer", 130000, "2021-07-12", 1),
        ("Grace Hopper", "grace@company.com", "Engineering", "Staff Engineer", 150000, "2020-02-28", 1),
        ("Hank Pym", "hank@company.com", "Engineering", "Junior Developer", 85000, "2023-01-10", 1),
        ("Ivy Chen", "ivy@company.com", "Marketing", "Content Strategist", 90000, "2022-04-15", 1),
        ("Jack Ryan", "jack@company.com", "Sales", "Sales Representative", 75000, "2023-06-01", 1),
        ("Karen Page", "karen@company.com", "Human Resources", "HR Specialist", 80000, "2022-09-01", 1),
        ("Liam Neeson", "liam@company.com", "Finance", "Financial Analyst", 95000, "2021-11-15", 1),
        ("Maya Lopez", "maya@company.com", "Engineering", "DevOps Engineer", 125000, "2022-01-20", 1),
        ("Nathan Drake", "nathan@company.com", "Sales", "Sales Associate", 65000, "2024-01-08", 1),
        ("Olivia Pope", "olivia@company.com", "Marketing", "Brand Manager", 105000, "2021-05-22", 0),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO employees (name, email, department, position, salary, hire_date, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
        employees,
    )

    # ── Projects ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            start_date TEXT,
            end_date TEXT,
            budget_allocated REAL DEFAULT 0
        )
    """)
    projects = [
        ("Project Atlas", "Engineering", "active", "2024-01-01", None, 120000),
        ("Brand Refresh", "Marketing", "completed", "2023-06-01", "2024-02-28", 80000),
        ("Q1 Sales Push", "Sales", "active", "2024-01-15", "2024-03-31", 50000),
        ("HR Portal", "Human Resources", "active", "2024-02-01", None, 45000),
        ("Cloud Migration", "Engineering", "active", "2023-09-01", None, 200000),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO projects (name, department, status, start_date, end_date, budget_allocated) VALUES (?, ?, ?, ?, ?, ?)",
        projects,
    )

    conn.commit()
    conn.close()
    print(f"✅ Demo database created at: {DB_PATH}")
    print(f"   Tables: departments (5 rows), employees (15 rows), projects (5 rows)")


if __name__ == "__main__":
    create_demo_database()
