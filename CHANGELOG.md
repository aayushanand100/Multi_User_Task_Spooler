# Changelog

All notable changes to the Multi-User Task Spooler with Deadlock Avoidance project will be documented in this file.

---

## [v1.2.0] - Email Notifications & User Email Input - 2026-11-15

### Overview
Replaced WhatsApp / Twilio notifications with native Email notifications and updated the website user inputs to collect user email addresses instead of phone numbers.

---

### 1. User Email Input & Schema Updates
- **Database Schema ([`database.py`](database.py))**:
  - Added `user_email TEXT DEFAULT ''` column to `tasks` table with automatic migration support.
  - Updated `create_task()` to accept and persist `user_email`.
  - Updated `complete_task()`, `get_all_tasks()`, and `get_task()` to include `user_email`.
- **Streamlit UI ([`app.py`](app.py))**:
  - Replaced the WhatsApp Phone Number input with a dedicated **User Email Address** field (`user@domain.com`).
  - Updated presets and queue cards to display user email addresses instead of phone numbers.

---

### 2. Native Email Notification Dispatcher ([`notification.py`](notification.py))
- **No Third-Party / Twilio Dependency**:
  - Uses Python's built-in `smtplib` and `email.mime` modules.
  - Generates both styled HTML and clean plain-text settlement emails.
- **Email Subject & Body**:
  - Subject: `[Task Spooler] Task #{task_id} Completed - Settlement Notice`
  - Body includes itemized bill breakdown, allocated devices, execution duration, and release status.
- **Dual-Mode Dispatching**:
  1. **Standard SMTP**: Connects to any standard SMTP server (e.g., Gmail, Outlook, AWS SES, or local relays) when credentials are provided.
  2. **Simulated Console + Instant `mailto:` Link**: When SMTP credentials are not configured, dispatches to console and provides a one-click `mailto:user@domain.com?subject=...&body=...` link that directly opens the user's default email client with pre-populated subject and message.

---

### 3. UI Settlement & Console Updates ([`app.py`](app.py))
- Replaced WhatsApp toggle with **"📧 Email Settlement Alerts"** toggle and optional SMTP server settings expander.
- Updated the post-completion banner to display recipient email, settlement breakdown, and a **"✉️ Open in Email Client (mailto Link)"** action button.
- Updated Completed Tasks table with a clickable **"✉️ Open Email"** action column.
- Console displays `📧 [EMAIL DISPATCHED]` logs upon task settlement.

---

## [v1.1.0] - Boss Priority, Lifecycle Audit Trail & WhatsApp Settlement - 2026-11-11

### Overview
Major feature upgrade introducing multi-tier role-based queue bypass scheduling (`Boss Priority`), fine-grained database state machine auditing (`task_lifecycle_logs`), and automated completion settlement with WhatsApp notification dispatch.

---

### 1. User Role & Boss Priority Scheduling
- **Schema Update (`tasks` table)**:
  - Added `user_role TEXT NOT NULL DEFAULT 'Standard User' CHECK (user_role IN ('Boss', 'Senior Staff', 'Standard User'))`.
  - Added `phone_number TEXT DEFAULT ''` for automated WhatsApp alerts.
- **Boss Scheduling Rule**:
  - Tasks submitted by a **'Boss'** bypass all lower-priority standard and senior staff queues, achieving the absolute lowest waiting time.
  - Queue evaluation order updated in raw SQL and dispatch loop:
    ```sql
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
    ```
- **UI Enhancements**:
  - Role pills in UI: `👑 Boss` (gold/amber), `💼 Senior Staff` (purple), and `👤 Standard User` (slate).
  - Quick preset: **"Load Boss Queue Bypass Scenario"** demonstrating a Boss task (P1) jumping ahead of a Standard User (P5).

---

### 2. Granular Database Lifecycle & Audit Logging
- **New Table (`task_lifecycle_logs`)**:
  - `log_id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
  - `task_id` (`INTEGER`, Foreign Key to `tasks.task_id` `ON DELETE CASCADE`)
  - `old_state` (`TEXT`)
  - `new_state` (`TEXT NOT NULL`)
  - `timestamp` (`TIMESTAMP DEFAULT CURRENT_TIMESTAMP`)
  - `notes` (`TEXT`)
- **Explicit State Machine Recording**:
  An immutable audit entry is written every single time a task changes state:
  1. `NONE ➔ QUEUED`: Task submission with declared demands and role tier.
  2. `QUEUED / BLOCKED ➔ RUNNING`: Banker's algorithm confirms safe state and allocates devices.
  3. `QUEUED ➔ BLOCKED`: Deadlock avoidance triggered; unsafe state detected.
  4. `RUNNING ➔ COMPLETED`: Task finished, resources restored to pool, and billing settled.
- **Streamlit Audit Tab**:
  - Added dedicated tab: **"Live DB Lifecycle Audit Trail"** displaying real-time transition records with timestamps and operational notes.

---

### 3. Completion Settlement & WhatsApp Notification
- **Simulated Billing Settlement**:
  - Calculates cost when a task completes:
    $$\text{Billing Amount (₹)} = (\text{total\_allocated\_units} \times \text{duration\_seconds} \times 1.50) + 25.00$$
  - Base fee: ₹25.00; unit rate: ₹1.50 per unit-second.
  - Automatically records `completed_at` timestamp and `billing_amount` in `tasks`.
- **WhatsApp Notification Integration (`notification.py`)**:
  - Template Message:
    > *"Hello {user_name}, your spooler task #{task_id} is completed! Resources released. Total bill: ₹{amount}. Status: DONE."*
  - **Dual-Mode Dispatching**:
    1. **Twilio WhatsApp API**: Ready to dispatch live WhatsApp messages using Twilio REST API credentials (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`).
    2. **Instant One-Click wa.me Deep Links**: When credentials are unset, dispatches simulated console alerts and renders an instant one-click `https://wa.me/{phone}?text={encoded_message}` link button.
  - UI Notification Toggle and Twilio configuration expander in sidebar.
  - Persistent completion settlement banner with instant WhatsApp launch.

---

## [v1.0.0] - Initial Implementation - 2026-11-11

### Overview
Initial release of the **Multi-User Task Spooler with Deadlock Avoidance**, a standalone Python web application simulating operating system resource scheduling using **Dijkstra's Banker's Algorithm** with priority dispatching and SQLite persistence.

---

### 1. Database Schema Design (`database.py`)
Built on SQLite (`spooler.db`) using raw SQL with strict transactional guarantees via explicit context managers (`BEGIN IMMEDIATE`, `COMMIT`, and `ROLLBACK`), foreign key constraints (`PRAGMA foreign_keys = ON;`), and atomic operations.

- **`resources`**:
  - `resource_id` (`TEXT PRIMARY KEY`): Unique name of the hardware resource.
  - `total_instances` (`INTEGER`): Total physical units configured.
  - `available_instances` (`INTEGER`): Units currently free for allocation ($0 \le \text{available} \le \text{total}$).
  - *Default Seed Data:*
    - `"High-Speed Laser Printer"`: 2 units
    - `"Color Plotter"`: 1 unit
    - `"3D Scanner"`: 2 units

- **`tasks`**:
  - `task_id` (`INTEGER PRIMARY KEY AUTOINCREMENT`): Auto-incremented unique task ID.
  - `user_name` (`TEXT`): Submitting user or job identifier.
  - `priority` (`INTEGER`): Job priority level ($1$ to $5$, where $5$ is highest).
  - `status` (`TEXT`): One of `'QUEUED'`, `'RUNNING'`, `'BLOCKED'`, or `'COMPLETED'`.
  - `created_at` (`TIMESTAMP DEFAULT CURRENT_TIMESTAMP`): Submission timestamp.

- **`allocations`**:
  - `task_id` (`INTEGER`, Foreign Key referencing `tasks(task_id)` `ON DELETE CASCADE`).
  - `resource_id` (`TEXT`, Foreign Key referencing `resources(resource_id)` `ON DELETE CASCADE`).
  - `allocated_units` (`INTEGER`): Currently held instances ($0$ when queued/blocked).
  - `requested_units` (`INTEGER`): Units requested to start or add.
  - `max_demand` (`INTEGER`): Maximum claim declared by the job.
  - Composite Primary Key: `(task_id, resource_id)`.

- **`safety_logs`**:
  - `log_id` (`INTEGER PRIMARY KEY AUTOINCREMENT`): Unique audit event ID.
  - `timestamp` (`TIMESTAMP`): Event timestamp.
  - `task_id` (`INTEGER`, Foreign Key referencing `tasks(task_id)`).
  - `event_type` (`TEXT`): `'SAFETY_CHECK_PASSED'`, `'SAFETY_CHECK_FAILED'`, `'TASK_COMPLETED'`, etc.
  - `message` (`TEXT`): Summary message.
  - `details` (`TEXT`): Step-by-step trace of the safety sequence and Work vectors.

---

### 2. Core Algorithm Logic (`banker.py`)

#### A. Banker's Algorithm (Safety State Check)
When a task in `QUEUED` or `BLOCKED` status is evaluated for dispatch:
1. **Physical Availability Test:**
   $$\forall j \in \text{Resources},\quad \text{Request}[j] \le \text{Available}[j]$$
   If any requested resource exceeds currently available instances, the task cannot run immediately and remains `BLOCKED`.
2. **Tentative Allocation (Simulation):**
   $$\text{Work} = \text{Available} - \text{Request}$$
   $$\text{Allocation}'[\text{candidate}] = \text{Allocation}[\text{candidate}] + \text{Request}$$
   $$\text{Need}'[\text{candidate}] = \text{MaxDemand}[\text{candidate}] - \text{Allocation}'[\text{candidate}]$$
3. **Safety State Search:**
   - Active processes considered: all currently `RUNNING` tasks plus the candidate task.
   - Vector $\text{Finish}[i] = \text{False}$ for all active tasks.
   - Greedily find an unfinished task $T_i$ such that $\text{Need}'[i] \le \text{Work}$.
   - If found:
     $$\text{Work} = \text{Work} + \text{Allocation}'[i]$$
     $$\text{Finish}[i] = \text{True}$$
     Append $T_i$ to $\text{SafeSequence}$.
   - Repeat until all active tasks finish or no task can proceed.
4. **Decision:**
   - **SAFE State:** If all active tasks finish, a safe execution sequence $\langle T_1, T_2, \dots \rangle$ exists. The allocation is committed to the database, resources are deducted, and task status is set to `'RUNNING'`.
   - **UNSAFE State (Deadlock Avoidance):** If no safe sequence exists, granting the resources could lead to a circular wait deadlock. The tentative allocation is discarded, and the task status is set to `'BLOCKED'`.

#### B. Priority Dispatching
- The queue is evaluated with tasks ordered by:
  $$\text{priority DESC},\quad \text{created\_at ASC}$$
- Higher priority tasks ($P5 > P4 > \dots > P1$) are tested for allocation before lower priority tasks. Ties are resolved by arrival order (FIFO).

#### C. Release & Automatic Queue Re-evaluation
- When a running task is marked `'COMPLETED'`:
  1. All held units ($\text{allocated\_units}$) are returned to $\text{available\_instances}$ in an explicit transaction.
  2. The task status is updated to `'COMPLETED'`.
  3. All waiting tasks (`BLOCKED` and `QUEUED`) are automatically re-evaluated in priority order.

---

### 3. Streamlit Interface (`app.py`)
- **Top Metrics Bar:** Displays Total Tasks, Running Tasks, Blocked Tasks, and Live Resource Availability with visual progress indicators.
- **Left Sidebar:**
  - Form to submit new jobs with User Name, Priority slider ($1$ to $5$), and quantity inputs for each resource.
  - Optional Advanced Hold-and-Wait toggle to demonstrate partial allocation.
  - One-click presets: *Deadlock Risk Scenario* and *Priority Batch (3 Tasks)*.
  - Manual Dispatch and Reset Database buttons.
- **Center/Main View:**
  - **System Safety Log:** Live terminal-style console box detailing the exact rationale for approving or blocking tasks, including simulated Work vectors and safe sequences.
  - **Running Tasks:** Dedicated cards with a **"Complete Task"** button next to each running task to release resources.
  - **Waiting Queue:** Displays priority badges, status badges, and an on-demand "Test / Dispatch" button.
  - **Banker's State Matrices:** Live view of the Available vector, Allocation matrix, Max Demand matrix, and Need matrix.

---

### 4. How to Run the Application

#### Prerequisites
- Python 3.9+
- pip

#### Step 1: Clone or Navigate to the Directory
```bash
cd "Task Spooler"
```

#### Step 2: (Optional) Set up Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Step 3: Install Required Dependencies
```bash
pip install -r requirements.txt
```

#### Step 4: Launch the Streamlit App
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.
