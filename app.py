"""
app.py - Streamlit Web Application
Multi-User Task Spooler with Deadlock Avoidance (Banker's Algorithm),
Boss Priority Scheduling, DB Lifecycle Audit Trail, and Email Settlement.
"""

import streamlit as st
import pandas as pd
import datetime
import os
from typing import Dict, Any, List

import database
import banker
import notification

# Ensure database tables exist and are initialized
database.init_db()

# Page configuration
st.set_page_config(
    page_title="Task Spooler | Banker's Algorithm & Email Settlement",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for badges, status styling, terminal console, and role pills
st.markdown("""
<style>
    .main-title {
        font-size: 2.15rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
        color: #0F172A;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #475569;
        margin-bottom: 1.5rem;
    }
    .badge-running {
        background-color: #DCFCE7;
        color: #15803D;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.82rem;
        border: 1px solid #86EFAC;
        display: inline-block;
    }
    .badge-blocked {
        background-color: #FEE2E2;
        color: #B91C1C;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.82rem;
        border: 1px solid #FCA5A5;
        display: inline-block;
    }
    .badge-queued {
        background-color: #E0F2FE;
        color: #0369A1;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.82rem;
        border: 1px solid #7DD3FC;
        display: inline-block;
    }
    .badge-completed {
        background-color: #F1F5F9;
        color: #334155;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.82rem;
        border: 1px solid #CBD5E1;
        display: inline-block;
    }
    .role-pill {
        padding: 3px 9px;
        border-radius: 6px;
        font-size: 0.82rem;
        font-weight: 700;
        display: inline-block;
    }
    .role-boss {
        background-color: #FEF3C7;
        color: #92400E;
        border: 1px solid #FCD34D;
    }
    .role-senior {
        background-color: #EDE9FE;
        color: #5B21B6;
        border: 1px solid #C4B5FD;
    }
    .role-standard {
        background-color: #F3F4F6;
        color: #374151;
        border: 1px solid #E5E7EB;
    }
    .priority-pill {
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.85rem;
        display: inline-block;
    }
    .priority-5 { background-color: #EDE9FE; color: #6D28D9; }
    .priority-4 { background-color: #DBEAFE; color: #1D4ED8; }
    .priority-3 { background-color: #FEF3C7; color: #B45309; }
    .priority-2 { background-color: #F3F4F6; color: #4B5563; }
    .priority-1 { background-color: #F8FAFC; color: #94A3B8; }

    .console-box {
        background-color: #0F172A;
        color: #38BDF8;
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.90rem;
        padding: 16px;
        border-radius: 8px;
        border: 1px solid #334155;
        white-space: pre-wrap;
        word-break: break-word;
        max-height: 280px;
        overflow-y: auto;
    }
    .console-success { color: #4ADE80; }
    .console-danger { color: #F87171; }
    .console-info { color: #93C5FD; }
    .console-email { color: #60A5FA; }

    .transition-tag {
        font-family: monospace;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 4px;
        background-color: #F1F5F9;
        color: #0F172A;
        border: 1px solid #CBD5E1;
        display: inline-block;
    }
    .settlement-card {
        background: linear-gradient(135deg, #EFF6FF 0%, #F0FDF4 100%);
        border: 1px solid #BFDBFE;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


# --- Helper Rendering Functions ---

def render_status_badge(status: str) -> str:
    s = status.upper()
    if s == "RUNNING":
        return '<span class="badge-running">● RUNNING</span>'
    elif s == "BLOCKED":
        return '<span class="badge-blocked">⚠️ BLOCKED</span>'
    elif s == "QUEUED":
        return '<span class="badge-queued">⏱️ QUEUED</span>'
    elif s == "COMPLETED":
        return '<span class="badge-completed">✓ COMPLETED</span>'
    return status


def render_user_role_pill(role: str) -> str:
    r = role or "Standard User"
    if r == "Boss":
        return '<span class="role-pill role-boss">👑 Boss</span>'
    elif r == "Senior Staff":
        return '<span class="role-pill role-senior">💼 Senior Staff</span>'
    return '<span class="role-pill role-standard">👤 Standard</span>'


def render_priority_pill(priority: int) -> str:
    return f'<span class="priority-pill priority-{priority}">P{priority}</span>'


# --- Data Retrieval ---
all_resources = database.get_all_resources()
all_tasks = database.get_all_tasks()
all_allocations = database.get_all_allocations()
recent_logs = database.get_latest_safety_logs(limit=30)
lifecycle_logs = database.get_task_lifecycle_logs(limit=100)

# Metrics calculation
total_tasks_count = len(all_tasks)
running_tasks = [t for t in all_tasks if t["status"] == "RUNNING"]
blocked_tasks = [t for t in all_tasks if t["status"] == "BLOCKED"]
queued_tasks = [t for t in all_tasks if t["status"] == "QUEUED"]
completed_tasks = [t for t in all_tasks if t["status"] == "COMPLETED"]
total_billed_inr = sum(t.get("billing_amount", 0.0) or 0.0 for t in completed_tasks)

# Header
st.markdown('<div class="main-title">Multi-User Task Spooler with Deadlock Avoidance</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Dijkstra\'s Banker\'s Algorithm • Boss Priority Scheduling • Email Completion Settlement</div>', unsafe_allow_html=True)


# --- Top Metrics Bar ---
col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
with col_m1:
    st.metric(label="Total Tasks", value=total_tasks_count, delta=f"{len(completed_tasks)} completed")
with col_m2:
    st.metric(label="Running Tasks", value=len(running_tasks), delta="Holding devices")
with col_m3:
    st.metric(label="Blocked (Avoidance)", value=len(blocked_tasks), delta=f"{len(queued_tasks)} queued", delta_color="inverse")
with col_m4:
    total_avail = sum(r["available_instances"] for r in all_resources)
    total_units = sum(r["total_instances"] for r in all_resources)
    st.metric(label="Available Units", value=f"{total_avail} / {total_units}", delta=f"{int((total_avail/max(1,total_units))*100)}% free")
with col_m5:
    st.metric(label="Settled Billing", value=f"₹{total_billed_inr:.2f}", delta=f"{len(completed_tasks)} settlements")

st.markdown("---")

# Live Resource Availability Bar
st.markdown("##### 🖨️ Live Device Pool Availability")
res_cols = st.columns(len(all_resources))
for idx, res in enumerate(all_resources):
    with res_cols[idx]:
        avail = res["available_instances"]
        tot = res["total_instances"]
        pct = avail / max(1, tot)
        st.markdown(f"**{res['resource_id']}**")
        st.caption(f"Free: **{avail}** / {tot} units")
        st.progress(pct)

st.markdown("<br>", unsafe_allow_html=True)


# --- Left Sidebar: Form & Controls ---
with st.sidebar:
    st.header("📝 Submit New Task")
    st.caption("Configure user role, priority, and resource demands.")

    with st.form(key="task_submission_form", clear_on_submit=False):
        user_name_input = st.text_input("User Name", value="Alice_Director", placeholder="e.g. Alice, Bob")
        
        # User Role selection
        user_role_input = st.selectbox(
            "User Role",
            options=["Standard User", "Senior Staff", "Boss"],
            index=2,
            help="Scheduling Rule: 'Boss' tasks bypass lower-priority queues to achieve the lowest waiting time."
        )

        # User Email input (replacing phone number)
        user_email_input = st.text_input(
            "User Email Address",
            value="alice.director@company.com",
            placeholder="e.g. user@domain.com",
            help="Email address for completion notices and billing settlements."
        )

        priority_slider = st.slider(
            "Job Priority (1 to 5)",
            min_value=1,
            max_value=5,
            value=3,
            help="Priority 5 evaluated before Priority 1 within the same role tier."
        )

        st.markdown("---")
        st.markdown("###### Resource Demands")
        st.caption("Units requested from each hardware device:")

        demands_input: Dict[str, Dict[str, int]] = {}
        
        demo_partial = st.checkbox(
            "Advanced: Partial Request (Hold-and-Wait)",
            value=False,
            help="Specify fewer initial units than max demand to test classic Banker's algorithm safe sequence resolution."
        )

        for res in all_resources:
            r_id = res["resource_id"]
            tot = res["total_instances"]
            
            if not demo_partial:
                q = st.number_input(
                    f"{r_id} (Max {tot})",
                    min_value=0,
                    max_value=tot,
                    value=1 if tot > 1 else 0,
                    step=1,
                    key=f"dem_{r_id}"
                )
                demands_input[r_id] = {"max_demand": int(q), "requested_units": int(q)}
            else:
                st.markdown(f"**{r_id}**")
                col_dm, col_dr = st.columns(2)
                with col_dm:
                    max_d = st.number_input(
                        "Max Demand",
                        min_value=0,
                        max_value=tot,
                        value=min(2, tot),
                        step=1,
                        key=f"max_{r_id}"
                    )
                with col_dr:
                    req_u = st.number_input(
                        "Initial Req",
                        min_value=0,
                        max_value=int(max_d),
                        value=min(1, int(max_d)),
                        step=1,
                        key=f"req_{r_id}"
                    )
                demands_input[r_id] = {"max_demand": int(max_d), "requested_units": int(req_u)}

        submit_btn = st.form_submit_button("🚀 Submit to Spooler", use_container_width=True)

        if submit_btn:
            total_req = sum(d["max_demand"] for d in demands_input.values())
            if not user_name_input.strip():
                st.error("Please enter a valid user or job name.")
            elif not user_email_input.strip():
                st.error("Please enter a valid user email address.")
            elif total_req == 0:
                st.warning("Please allocate at least 1 unit of any resource.")
            else:
                new_task_id = database.create_task(
                    user_name=user_name_input.strip(),
                    priority=priority_slider,
                    resource_demands=demands_input,
                    user_role=user_role_input,
                    user_email=user_email_input.strip()
                )
                banker.dispatch_queue()
                st.success(f"Task #{new_task_id} submitted for '{user_email_input.strip()}'!")
                st.rerun()

    st.markdown("---")
    st.subheader("📧 Email Settlement Alerts")
    email_toggle = st.toggle("Enable Email Notification on Completion", value=True)

    with st.expander("SMTP Email Server Settings (Optional)", expanded=False):
        st.caption("Leave blank to use instant simulated console dispatch and direct mailto: one-click links.")
        smtp_h = st.text_input("SMTP Host", value=os.environ.get("SMTP_HOST", ""), placeholder="e.g. smtp.gmail.com")
        smtp_p = st.number_input("SMTP Port", value=int(os.environ.get("SMTP_PORT", 587)), min_value=1, max_value=65535)
        smtp_u = st.text_input("SMTP Username", value=os.environ.get("SMTP_USER", ""), placeholder="user@gmail.com")
        smtp_pw = st.text_input("SMTP Password", value=os.environ.get("SMTP_PASS", ""), type="password")
        smtp_f = st.text_input("Sender From Email", value=os.environ.get("SMTP_FROM", "spooler@company.com"))
        smtp_cfg = {
            "smtp_host": smtp_h.strip(),
            "smtp_port": smtp_p,
            "smtp_user": smtp_u.strip(),
            "smtp_pass": smtp_pw.strip(),
            "smtp_from": smtp_f.strip()
        }

    st.markdown("---")
    st.subheader("🧪 Quick Test Presets")

    # Preset 1: Boss Priority Queue Bypass Demonstration
    if st.button("👑 Load Boss Queue Bypass Scenario", use_container_width=True, help="Submits a Standard User task with Priority 5, then a Boss task with Priority 1. Demonstrates how the Boss task jumps to the front of the queue!"):
        database.reset_database()
        database.create_task("Staff_Bob", 5, {
            "High-Speed Laser Printer": {"max_demand": 2, "requested_units": 2},
            "Color Plotter": {"max_demand": 0, "requested_units": 0},
            "3D Scanner": {"max_demand": 0, "requested_units": 0}
        }, user_role="Standard User", user_email="bob.staff@company.com")

        database.create_task("CEO_Alice", 1, {
            "High-Speed Laser Printer": {"max_demand": 1, "requested_units": 1},
            "Color Plotter": {"max_demand": 0, "requested_units": 0},
            "3D Scanner": {"max_demand": 0, "requested_units": 0}
        }, user_role="Boss", user_email="alice.ceo@company.com")

        banker.dispatch_queue()
        st.toast("Loaded Boss Bypass Scenario! Boss (P1) bypassed Standard User (P5).")
        st.rerun()

    # Preset 2: Deadlock Avoidance Demonstration
    if st.button("⚠️ Load Deadlock Risk Scenario", use_container_width=True, help="Creates a state where two tasks hold resources with overlapping future need. The second task will be BLOCKED to prevent deadlock."):
        database.reset_database()
        database.create_task("Alice", 5, {
            "High-Speed Laser Printer": {"max_demand": 2, "requested_units": 1},
            "Color Plotter": {"max_demand": 0, "requested_units": 0},
            "3D Scanner": {"max_demand": 2, "requested_units": 1}
        }, user_role="Senior Staff", user_email="alice.senior@studio.com")
        banker.dispatch_queue()

        database.create_task("Bob", 4, {
            "High-Speed Laser Printer": {"max_demand": 2, "requested_units": 1},
            "Color Plotter": {"max_demand": 0, "requested_units": 0},
            "3D Scanner": {"max_demand": 2, "requested_units": 1}
        }, user_role="Standard User", user_email="bob.dev@studio.com")
        banker.dispatch_queue()
        st.toast("Loaded Deadlock Risk Scenario! Bob is BLOCKED to avoid deadlock.")
        st.rerun()

    # Controls: Dispatch & Reset
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("🔄 Dispatch", use_container_width=True, help="Re-evaluate all queued and blocked tasks"):
            banker.dispatch_queue()
            st.rerun()
    with col_s2:
        if st.button("🗑️ Reset DB", use_container_width=True, help="Clear all tasks, logs, and restore default resources"):
            database.reset_database()
            st.rerun()


# --- Main View: System Safety Log Box ---
st.markdown("### 🛡️ System Safety & Settlement Console")

latest_log = recent_logs[0] if recent_logs else None
if latest_log:
    ev_type = latest_log["event_type"]
    msg = latest_log["message"]
    dtls = latest_log["details"] or ""
    ts = latest_log["timestamp"]

    if "PASSED" in ev_type:
        color_class = "console-success"
        icon = "✅ [SAFE STATE]"
    elif "FAILED" in ev_type:
        color_class = "console-danger"
        icon = "🛑 [DEADLOCK AVOIDED]"
    elif "EMAIL" in ev_type:
        color_class = "console-email"
        icon = "📧 [EMAIL DISPATCHED]"
    elif "COMPLETED" in ev_type:
        color_class = "console-info"
        icon = "🔄 [RESOURCES RELEASED]"
    else:
        color_class = "console-info"
        icon = "ℹ️ [SYSTEM]"

    console_content = f"{ts} | {icon} {msg}\n\n{dtls}"
    st.markdown(f'<div class="console-box {color_class}">{console_content}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="console-box console-info">System initialized. Ready to process multi-user spooler tasks.</div>', unsafe_allow_html=True)


st.markdown("<br>", unsafe_allow_html=True)


# --- Tabs: Tasks, Waiting Queue, Completed/Settled, DB Lifecycle Audit Trail, Banker's Matrices ---
tab_running, tab_waiting, tab_completed, tab_audit, tab_matrix = st.tabs([
    f"🟢 Running ({len(running_tasks)})",
    f"⏳ Queue & Blocked ({len(queued_tasks) + len(blocked_tasks)})",
    f"✔️ Completed & Settled ({len(completed_tasks)})",
    f"📜 Live DB Lifecycle Audit Trail ({len(lifecycle_logs)})",
    "📊 Banker's State Matrices"
])

# Group allocations by task_id
allocations_by_task: Dict[int, Dict[str, Dict[str, int]]] = {}
for a in all_allocations:
    tid = a["task_id"]
    if tid not in allocations_by_task:
        allocations_by_task[tid] = {}
    allocations_by_task[tid][a["resource_id"]] = {
        "allocated": a["allocated_units"],
        "max": a["max_demand"]
    }


# TAB 1: RUNNING TASKS
with tab_running:
    if not running_tasks:
        st.info("No tasks are currently running. Submit a job from the sidebar or click a quick preset.")
    else:
        for t in running_tasks:
            tid = t["task_id"]
            user = t["user_name"]
            role = t.get("user_role", "Standard User")
            prio = t["priority"]
            created = t["created_at"]
            started = t.get("started_at") or created
            email = t.get("user_email") or ""
            t_alloc = allocations_by_task.get(tid, {})

            alloc_summary = ", ".join([
                f"{r}: {info['allocated']}/{info['max']}"
                for r, info in t_alloc.items() if info['max'] > 0
            ]) or "None"

            with st.container():
                c_id, c_user, c_role, c_prio, c_alloc, c_action = st.columns([1, 2, 1.5, 1, 3, 2.5])
                with c_id:
                    st.markdown(f"**Task #{tid}**")
                    st.caption(f"Started: {started}")
                with c_user:
                    st.markdown(f"**{user}**")
                    st.markdown(render_status_badge(t["status"]), unsafe_allow_html=True)
                with c_role:
                    st.markdown(render_user_role_pill(role), unsafe_allow_html=True)
                with c_prio:
                    st.markdown(render_priority_pill(prio), unsafe_allow_html=True)
                with c_alloc:
                    st.markdown(f"**Allocated / Max:** `{alloc_summary}`")
                    if email:
                        st.caption(f"✉️ `{email}`")
                with c_action:
                    # Complete Task button: Releases resources, settles bill, and dispatches email notification
                    if st.button("✅ Complete & Settle", key=f"complete_{tid}", use_container_width=True, type="primary"):
                        res = banker.release_and_dispatch(
                            task_id=tid,
                            smtp_config=smtp_cfg,
                            send_notification=email_toggle
                        )
                        settle_info = res["settlement"]
                        notif_info = res["notification"]
                        
                        st.toast(f"Task #{tid} completed! Bill settled: ₹{settle_info.get('billing_amount', 0):.2f}.")
                        if notif_info:
                            st.session_state["latest_settlement"] = {
                                "task_id": tid,
                                "user_name": user,
                                "email": notif_info["email"],
                                "subject": notif_info["subject"],
                                "bill": settle_info.get("billing_amount", 0.0),
                                "body_text": notif_info["body_text"],
                                "mailto_link": notif_info["mailto_link"]
                            }
                        st.rerun()
            st.divider()

    # Show alert banner if a settlement just occurred
    if "latest_settlement" in st.session_state:
        s_data = st.session_state["latest_settlement"]
        with st.container():
            st.markdown(f"""
            <div class="settlement-card">
                <h4 style="margin:0 0 8px 0; color:#1E40AF;">📧 Settlement Notice Sent for Task #{s_data['task_id']} ({s_data['user_name']})</h4>
                <p style="margin:0 0 8px 0; color:#1E3A8A; font-weight:600;">Recipient: <code>{s_data['email']}</code> • Total Bill: ₹{s_data['bill']:.2f} • Hardware Restored</p>
                <div style="background:#FFFFFF; border:1px solid #BFDBFE; border-radius:6px; padding:10px; margin-bottom:12px; font-family:monospace; font-size:0.88rem; white-space:pre-wrap;">{s_data['body_text']}</div>
                <a href="{s_data['mailto_link']}" target="_blank" style="display:inline-block; background-color:#2563EB; color:#FFFFFF; padding:8px 16px; border-radius:6px; text-decoration:none; font-weight:700;">✉️ Open in Email Client (mailto Link)</a>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Dismiss Settlement Banner", key="dismiss_settlement"):
                del st.session_state["latest_settlement"]
                st.rerun()


# TAB 2: WAITING QUEUE & BLOCKED TASKS
with tab_waiting:
    waiting_tasks = [t for t in all_tasks if t["status"] in ("BLOCKED", "QUEUED")]
    if not waiting_tasks:
        st.success("The queue is empty! No tasks are blocked or queued.")
    else:
        st.caption("Ordered by: **Boss First** (`user_role = 'Boss'`), then **Priority** (`DESC`), then **Arrival Time** (`ASC`).")
        for t in waiting_tasks:
            tid = t["task_id"]
            user = t["user_name"]
            role = t.get("user_role", "Standard User")
            prio = t["priority"]
            status = t["status"]
            created = t["created_at"]
            t_alloc = allocations_by_task.get(tid, {})

            demand_summary = ", ".join([
                f"{r}: {info['max']}"
                for r, info in t_alloc.items() if info['max'] > 0
            ]) or "None"

            with st.container():
                c_id, c_user, c_role, c_prio, c_status, c_dem, c_retry = st.columns([1, 2, 1.5, 1, 2, 2.5, 2])
                with c_id:
                    st.markdown(f"**Task #{tid}**")
                    st.caption(f"{created}")
                with c_user:
                    st.markdown(f"**{user}**")
                with c_role:
                    st.markdown(render_user_role_pill(role), unsafe_allow_html=True)
                with c_prio:
                    st.markdown(render_priority_pill(prio), unsafe_allow_html=True)
                with c_status:
                    st.markdown(render_status_badge(status), unsafe_allow_html=True)
                with c_dem:
                    st.markdown(f"**Demands:** `{demand_summary}`")
                with c_retry:
                    if st.button("🔍 Dispatch Test", key=f"retry_{tid}", use_container_width=True):
                        eval_res = banker.evaluate_and_dispatch_task(tid)
                        if eval_res["success"]:
                            st.toast(f"Task #{tid} approved and moved to RUNNING!")
                        else:
                            st.toast(f"Task #{tid} remains BLOCKED (Deadlock Avoidance).")
                        st.rerun()
            st.divider()


# TAB 3: COMPLETED & SETTLED TASKS
with tab_completed:
    if not completed_tasks:
        st.info("No completed tasks yet. Finish a running task to calculate bill and dispatch email alert.")
    else:
        st.caption("Tasks settled and resources returned to pool.")
        comp_records = []
        for t in completed_tasks:
            tid = t["task_id"]
            user = t["user_name"]
            role = t.get("user_role", "Standard User")
            email = t.get("user_email") or ""
            amount = t.get("billing_amount", 0.0) or 0.0
            subject = notification.format_email_subject(tid)
            body = notification.format_email_body_text(user, tid, amount)
            mailto_link = notification.get_mailto_link(email, subject, body)

            comp_records.append({
                "Task ID": f"#{tid}",
                "User": user,
                "Role": role,
                "Priority": f"P{t['priority']}",
                "Status": t["status"],
                "Total Bill": f"₹{amount:.2f}",
                "User Email": email or "N/A",
                "Completed At": t.get("completed_at") or t["created_at"],
                "Email Notice": mailto_link
            })

        comp_df = pd.DataFrame(comp_records)
        st.dataframe(
            comp_df,
            column_config={
                "Email Notice": st.column_config.LinkColumn(
                    "Email Notice",
                    display_text="✉️ Open Email"
                )
            },
            use_container_width=True,
            hide_index=True
        )


# TAB 4: LIVE DB LIFECYCLE AUDIT TRAIL (Granular State Machine)
with tab_audit:
    st.markdown("#### 📜 Live Database Lifecycle Audit Trail (`task_lifecycle_logs`)")
    st.caption("Immutable state machine event history recorded on every state transition (QUEUED ➔ RUNNING ➔ BLOCKED ➔ COMPLETED).")

    if not lifecycle_logs:
        st.info("No lifecycle transitions recorded yet.")
    else:
        audit_rows = []
        for l in lifecycle_logs:
            old_s = l["old_state"] or "NONE"
            new_s = l["new_state"]
            transition = f"{old_s} ➔ {new_s}"
            audit_rows.append({
                "Log ID": l["log_id"],
                "Timestamp": l["timestamp"],
                "Task ID": f"#{l['task_id']}",
                "User": l.get("user_name") or f"Task #{l['task_id']}",
                "Role": l.get("user_role") or "Standard User",
                "Email": l.get("user_email") or "N/A",
                "State Transition": transition,
                "Audit Notes": l["notes"]
            })

        audit_df = pd.DataFrame(audit_rows)
        st.dataframe(audit_df, use_container_width=True, hide_index=True)


# TAB 5: BANKER'S STATE MATRICES (Deep OS Concept View)
with tab_matrix:
    st.markdown("#### 🔬 Operating System Banker's State Matrices")
    st.caption("Live mathematical vectors and matrices used during safety state evaluations.")

    res_ids, avail_vec, tot_vec, tasks_matrix = banker.get_active_tasks_and_matrices()

    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.markdown("**Available Vector (Work)**")
        st.dataframe(pd.DataFrame([avail_vec], index=["Available"]), use_container_width=True)
    with col_v2:
        st.markdown("**Total Resource Capacity**")
        st.dataframe(pd.DataFrame([tot_vec], index=["Total"]), use_container_width=True)

    if tasks_matrix:
        st.markdown("**Active Process Matrices (Allocation, Max Demand, and Need)**")
        matrix_rows = []
        for tid, tinfo in tasks_matrix.items():
            row = {
                "Task": f"#{tid} ({tinfo['user_name']})",
                "Role": tinfo["user_role"],
                "Status": tinfo["status"],
                "Priority": tinfo["priority"]
            }
            for r in res_ids:
                alloc_val = tinfo["allocation"][r]
                max_val = tinfo["max_demand"][r]
                need_val = tinfo["need"][r]
                row[f"{r} [Alloc]"] = alloc_val
                row[f"{r} [Max]"] = max_val
                row[f"{r} [Need]"] = need_val
            matrix_rows.append(row)

        st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No active tasks in the system to populate matrices.")

    st.markdown("""
    > **Boss Scheduling Invariant:** When multiple tasks are queued or blocked, the dispatch scheduler prioritizes `user_role = 'Boss'` over standard priority levels. Once ordered, Dijkstra's Banker's algorithm evaluates each candidate: tentative allocation is granted if and only if a safe sequence $\\langle T_1, T_2, \\dots, T_n \\rangle$ can satisfy all active tasks' future demands without risk of circular wait deadlock.
    """)
