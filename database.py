"""
database.py - Database Schema and Transaction Layer for Task Spooler
Uses SQLite with raw SQL, explicit transaction handling, and granular lifecycle auditing.
"""

import sqlite3
import os
import datetime
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple, Any

DB_FILE = "spooler.db"

DEFAULT_RESOURCES = [
    ("High-Speed Laser Printer", 2, 2),
    ("Color Plotter", 1, 1),
    ("3D Scanner", 2, 2),
]


def get_db_path(db_path: Optional[str] = None) -> str:
    """Returns absolute or relative path to the database file."""
    return db_path or os.environ.get("SPOOLER_DB_PATH", DB_FILE)


def get_raw_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Creates a new SQLite connection with foreign keys enabled and row_factory configured.
    Explicit transaction control is managed via BEGIN / COMMIT / ROLLBACK.
    """
    path = get_db_path(db_path)
    conn = sqlite3.connect(path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def transaction_scope(db_path: Optional[str] = None):
    """
    Context manager providing explicit transaction handling:
    Executes 'BEGIN IMMEDIATE', yields connection, commits on success, rollbacks on error.
    """
    conn = get_raw_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        yield conn
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()


@contextmanager
def readonly_scope(db_path: Optional[str] = None):
    """Context manager for read-only queries with clean connection lifecycle."""
    conn = get_raw_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initializes database tables, migrations, and seeds default resources if not present.
    Uses explicit transaction handling.
    """
    with transaction_scope(db_path) as conn:
        cursor = conn.cursor()

        # Table: resources
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                resource_id TEXT PRIMARY KEY,
                total_instances INTEGER NOT NULL CHECK (total_instances >= 0),
                available_instances INTEGER NOT NULL CHECK (available_instances >= 0 AND available_instances <= total_instances)
            );
        """)

        # Table: tasks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                user_role TEXT NOT NULL DEFAULT 'Standard User' CHECK (user_role IN ('Boss', 'Senior Staff', 'Standard User')),
                priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
                status TEXT NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'BLOCKED', 'COMPLETED')),
                user_email TEXT DEFAULT '',
                phone_number TEXT DEFAULT '',
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                billing_amount REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Table: allocations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS allocations (
                task_id INTEGER NOT NULL,
                resource_id TEXT NOT NULL,
                allocated_units INTEGER NOT NULL DEFAULT 0 CHECK (allocated_units >= 0),
                requested_units INTEGER NOT NULL DEFAULT 0 CHECK (requested_units >= 0),
                max_demand INTEGER NOT NULL CHECK (max_demand >= 0),
                PRIMARY KEY (task_id, resource_id),
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
                FOREIGN KEY (resource_id) REFERENCES resources (resource_id) ON DELETE CASCADE
            );
        """)

        # Table: safety_logs (Audit log for Banker's algorithm evaluations)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS safety_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                task_id INTEGER,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE SET NULL
            );
        """)

        # Table: task_lifecycle_logs (Granular State Machine Audit Trail)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_lifecycle_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                old_state TEXT,
                new_state TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id) ON DELETE CASCADE
            );
        """)

        # Migrations: Check and add missing columns to tasks table
        cursor.execute("PRAGMA table_info(tasks);")
        t_cols = [row["name"] for row in cursor.fetchall()]
        if "user_role" not in t_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN user_role TEXT NOT NULL DEFAULT 'Standard User';")
        if "user_email" not in t_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN user_email TEXT DEFAULT '';")
        if "phone_number" not in t_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN phone_number TEXT DEFAULT '';")
        if "started_at" not in t_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN started_at TIMESTAMP;")
        if "completed_at" not in t_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN completed_at TIMESTAMP;")
        if "billing_amount" not in t_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN billing_amount REAL DEFAULT 0.0;")

        # Migrations: Check and add requested_units column to allocations table if missing
        cursor.execute("PRAGMA table_info(allocations);")
        a_cols = [row["name"] for row in cursor.fetchall()]
        if "requested_units" not in a_cols:
            cursor.execute("ALTER TABLE allocations ADD COLUMN requested_units INTEGER NOT NULL DEFAULT 0;")

        # Seed default resources if table is empty
        cursor.execute("SELECT COUNT(*) AS cnt FROM resources;")
        row = cursor.fetchone()
        if row and row["cnt"] == 0:
            cursor.executemany("""
                INSERT INTO resources (resource_id, total_instances, available_instances)
                VALUES (?, ?, ?);
            """, DEFAULT_RESOURCES)
            
            cursor.execute("""
                INSERT INTO safety_logs (event_type, message, details)
                VALUES ('SYSTEM_INIT', 'Database initialized with default resources.', 'Seed resources: Laser Printer (2), Color Plotter (1), 3D Scanner (2)');
            """)


def record_lifecycle_log(
    task_id: int,
    old_state: Optional[str],
    new_state: str,
    notes: str = "",
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str] = None
) -> None:
    """
    Inserts an immutable state transition record into task_lifecycle_logs.
    Uses existing connection if provided, else opens an explicit transaction.
    """
    query = """
        INSERT INTO task_lifecycle_logs (task_id, old_state, new_state, notes)
        VALUES (?, ?, ?, ?);
    """
    if conn:
        conn.execute(query, (task_id, old_state, new_state, notes))
    else:
        with transaction_scope(db_path) as c:
            c.execute(query, (task_id, old_state, new_state, notes))


def get_all_resources(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches all resources with total and available counts."""
    with readonly_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT resource_id, total_instances, available_instances FROM resources ORDER BY resource_id ASC;")
        return [dict(row) for row in cursor.fetchall()]


def get_all_tasks(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches all tasks with User Role and Boss Priority ordering:
    Boss tasks bypass lower priority queues to achieve lowest waiting time.
    """
    with readonly_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT task_id, user_name, user_role, priority, status, user_email, started_at, completed_at, billing_amount, created_at
            FROM tasks
            ORDER BY 
                CASE status
                    WHEN 'RUNNING' THEN 1
                    WHEN 'QUEUED' THEN 2
                    WHEN 'BLOCKED' THEN 3
                    WHEN 'COMPLETED' THEN 4
                    ELSE 5
                END,
                CASE WHEN user_role = 'Boss' THEN 0 ELSE 1 END,
                priority DESC,
                created_at ASC;
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_task(task_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetches single task by ID."""
    with readonly_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT task_id, user_name, user_role, priority, status, user_email, started_at, completed_at, billing_amount, created_at
            FROM tasks
            WHERE task_id = ?;
        """, (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_allocations_for_task(task_id: int, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches resource allocations for a specific task."""
    with readonly_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT resource_id, allocated_units, requested_units, max_demand
            FROM allocations
            WHERE task_id = ?
            ORDER BY resource_id ASC;
        """, (task_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_all_allocations(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches all allocations across all tasks."""
    with readonly_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT task_id, resource_id, allocated_units, requested_units, max_demand
            FROM allocations
            ORDER BY task_id ASC, resource_id ASC;
        """)
        return [dict(row) for row in cursor.fetchall()]


def create_task(
    user_name: str,
    priority: int,
    resource_demands: Dict[str, Dict[str, int]],
    user_role: str = "Standard User",
    user_email: str = "",
    db_path: Optional[str] = None
) -> int:
    """
    Creates a new task in QUEUED status with its resource demands, user role, and user email.
    Explicitly logs the initial lifecycle state transition: NONE -> QUEUED.
    """
    valid_roles = ("Boss", "Senior Staff", "Standard User")
    role = user_role if user_role in valid_roles else "Standard User"
    email = user_email.strip()

    with transaction_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (user_name, user_role, priority, status, user_email)
            VALUES (?, ?, ?, 'QUEUED', ?);
        """, (user_name.strip(), role, priority, email))
        task_id = cursor.lastrowid

        for res_id, demand_info in resource_demands.items():
            max_dem = demand_info.get("max_demand", 0)
            req_units = demand_info.get("requested_units", max_dem)
            alloc = demand_info.get("allocated_units", 0)
            cursor.execute("""
                INSERT INTO allocations (task_id, resource_id, allocated_units, requested_units, max_demand)
                VALUES (?, ?, ?, ?, ?);
            """, (task_id, res_id, alloc, req_units, max_dem))

        # Explicit Lifecycle Log: Submission to QUEUED
        record_lifecycle_log(
            task_id=task_id,
            old_state="NONE",
            new_state="QUEUED",
            notes=f"Job submitted by '{user_name}' [Role: {role}, Priority: {priority}, Email: {email or 'N/A'}]. Demands: {resource_demands}",
            conn=conn
        )

        cursor.execute("""
            INSERT INTO safety_logs (task_id, event_type, message, details)
            VALUES (?, 'TASK_SUBMITTED', ?, ?);
        """, (
            task_id,
            f"Task #{task_id} submitted by '{user_name}' ({role}, Priority {priority}). Status: QUEUED.",
            f"Email: {email or 'N/A'} | Demands: {resource_demands}"
        ))

        return task_id


def mark_task_running(
    task_id: int,
    allocated_resources: Dict[str, int],
    db_path: Optional[str] = None
) -> None:
    """
    Updates task status to RUNNING, increments allocated units, zeroes requested_units,
    deducts from resources.available_instances, and records the QUEUED/BLOCKED -> RUNNING lifecycle event.
    Executes in an explicit transaction.
    """
    with transaction_scope(db_path) as conn:
        cursor = conn.cursor()
        
        # Check current status
        cursor.execute("SELECT status, started_at FROM tasks WHERE task_id = ?;", (task_id,))
        task_row = cursor.fetchone()
        old_state = task_row["status"] if task_row else "QUEUED"
        
        # Deduct from available_instances
        for res_id, units in allocated_resources.items():
            if units > 0:
                cursor.execute("""
                    UPDATE resources
                    SET available_instances = available_instances - ?
                    WHERE resource_id = ? AND available_instances >= ?;
                """, (units, res_id, units))
                if cursor.rowcount == 0:
                    raise ValueError(f"Insufficient available units for resource '{res_id}'.")
                
                # Update allocation
                cursor.execute("""
                    UPDATE allocations
                    SET allocated_units = allocated_units + ?,
                        requested_units = 0
                    WHERE task_id = ? AND resource_id = ?;
                """, (units, task_id, res_id))

        # Update task status and started_at
        cursor.execute("""
            UPDATE tasks
            SET status = 'RUNNING',
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP)
            WHERE task_id = ?;
        """, (task_id,))

        # Granular Lifecycle Log: Transition to RUNNING
        record_lifecycle_log(
            task_id=task_id,
            old_state=old_state,
            new_state="RUNNING",
            notes=f"Banker's safety check passed. Granted allocation: {allocated_resources}.",
            conn=conn
        )


def mark_task_blocked(task_id: int, db_path: Optional[str] = None) -> None:
    """
    Updates task status to BLOCKED in an explicit transaction,
    and records the QUEUED/RUNNING -> BLOCKED lifecycle event.
    """
    with transaction_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM tasks WHERE task_id = ?;", (task_id,))
        task_row = cursor.fetchone()
        old_state = task_row["status"] if task_row else "QUEUED"

        cursor.execute("""
            UPDATE tasks
            SET status = 'BLOCKED'
            WHERE task_id = ?;
        """, (task_id,))

        # Granular Lifecycle Log: Transition to BLOCKED
        record_lifecycle_log(
            task_id=task_id,
            old_state=old_state,
            new_state="BLOCKED",
            notes="Deadlock avoidance triggered. State check failed, task blocked.",
            conn=conn
        )


def complete_task(task_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Marks a running task as 'COMPLETED', restoring all allocated units back to resources.
    Calculates execution duration and simulated billing settlement:
      billing_amount = (allocated_units * duration_seconds * 1.50) + base_fee
    Records the RUNNING -> COMPLETED lifecycle event.
    Executes within an explicit transaction.
    """
    released = {}
    settlement_result = {}

    with transaction_scope(db_path) as conn:
        cursor = conn.cursor()

        # Check current status and metadata
        cursor.execute("""
            SELECT status, user_name, user_role, user_email, started_at, created_at
            FROM tasks
            WHERE task_id = ?;
        """, (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            raise ValueError(f"Task #{task_id} does not exist.")
        if task_row["status"] == "COMPLETED":
            return {}

        old_state = task_row["status"]
        user_name = task_row["user_name"]
        user_role = task_row["user_role"]
        user_email = task_row["user_email"] or ""

        # Fetch allocated units
        cursor.execute("""
            SELECT resource_id, allocated_units
            FROM allocations
            WHERE task_id = ?;
        """, (task_id,))
        allocations = cursor.fetchall()

        total_allocated_units = 0
        for alloc in allocations:
            res_id = alloc["resource_id"]
            units = alloc["allocated_units"]
            total_allocated_units += units
            if units > 0:
                cursor.execute("""
                    UPDATE resources
                    SET available_instances = MIN(total_instances, available_instances + ?)
                    WHERE resource_id = ?;
                """, (units, res_id))
                released[res_id] = units

        # Compute duration
        cursor.execute("""
            SELECT CAST((strftime('%s', 'now') - strftime('%s', COALESCE(started_at, created_at))) AS INTEGER) AS elapsed
            FROM tasks WHERE task_id = ?;
        """, (task_id,))
        dur_row = cursor.fetchone()
        raw_elapsed = dur_row["elapsed"] if dur_row and dur_row["elapsed"] is not None else 0
        duration_seconds = max(15, raw_elapsed)

        # Billing settlement formula: (allocated_units * duration_seconds * 1.50) + 25.00
        base_fee = 25.00
        unit_rate = 1.50
        billing_amount = round((total_allocated_units * duration_seconds * unit_rate) + base_fee, 2)

        # Zero out allocated_units and requested_units
        cursor.execute("""
            UPDATE allocations
            SET allocated_units = 0, requested_units = 0
            WHERE task_id = ?;
        """, (task_id,))

        # Update task status, completed_at, and billing_amount
        cursor.execute("""
            UPDATE tasks
            SET status = 'COMPLETED',
                completed_at = CURRENT_TIMESTAMP,
                billing_amount = ?
            WHERE task_id = ?;
        """, (billing_amount, task_id))

        # Granular Lifecycle Log: Transition to COMPLETED
        notes_str = (
            f"Task finished. Released {released}. Settled billing: ₹{billing_amount:.2f} "
            f"({total_allocated_units} units * {duration_seconds}s * ₹{unit_rate} + ₹{base_fee} base)."
        )
        record_lifecycle_log(
            task_id=task_id,
            old_state=old_state,
            new_state="COMPLETED",
            notes=notes_str,
            conn=conn
        )

        # Log completion in safety_logs
        cursor.execute("""
            INSERT INTO safety_logs (task_id, event_type, message, details)
            VALUES (?, 'TASK_COMPLETED', ?, ?);
        """, (
            task_id,
            f"Task #{task_id} ('{user_name}') completed. Bill: ₹{billing_amount:.2f}.",
            f"Email: {user_email or 'N/A'} | Released: {released} | Duration: {duration_seconds}s | Bill: ₹{billing_amount:.2f}"
        ))

        settlement_result = {
            "task_id": task_id,
            "user_name": user_name,
            "user_role": user_role,
            "user_email": user_email,
            "total_units": total_allocated_units,
            "duration_seconds": duration_seconds,
            "billing_amount": billing_amount,
            "released_resources": released
        }

    return settlement_result


def get_task_lifecycle_logs(limit: int = 150, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches immutable state machine lifecycle logs joined with task details.
    """
    with readonly_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT l.log_id, l.timestamp, l.task_id, t.user_name, t.user_role, t.user_email, l.old_state, l.new_state, l.notes
            FROM task_lifecycle_logs l
            LEFT JOIN tasks t ON l.task_id = t.task_id
            ORDER BY l.log_id DESC
            LIMIT ?;
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def add_safety_log(
    event_type: str,
    message: str,
    details: str = "",
    task_id: Optional[int] = None,
    db_path: Optional[str] = None
) -> None:
    """Inserts a safety log entry into the safety_logs table."""
    with transaction_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO safety_logs (task_id, event_type, message, details)
            VALUES (?, ?, ?, ?);
        """, (task_id, event_type, message, details))


def get_latest_safety_logs(limit: int = 40, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves recent safety log entries in reverse chronological order."""
    with readonly_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT log_id, timestamp, task_id, event_type, message, details
            FROM safety_logs
            ORDER BY log_id DESC
            LIMIT ?;
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def reset_database(db_path: Optional[str] = None) -> None:
    """
    Clears all tasks, allocations, lifecycle logs, and safety logs,
    and restores default resource quantities. Uses explicit transaction handling.
    """
    with transaction_scope(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_lifecycle_logs;")
        cursor.execute("DELETE FROM allocations;")
        cursor.execute("DELETE FROM tasks;")
        cursor.execute("DELETE FROM safety_logs;")
        cursor.execute("DELETE FROM resources;")

        cursor.executemany("""
            INSERT INTO resources (resource_id, total_instances, available_instances)
            VALUES (?, ?, ?);
        """, DEFAULT_RESOURCES)

        cursor.execute("""
            INSERT INTO safety_logs (event_type, message, details)
            VALUES ('SYSTEM_RESET', 'System database reset to initial seed state.', 'Default resources restored.');
        """)
