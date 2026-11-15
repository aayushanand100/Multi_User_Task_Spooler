"""
banker.py - Banker's Algorithm (Deadlock Avoidance) and Priority Dispatcher
Implements Dijkstra's Banker's Algorithm, Boss Priority scheduling, and Email settlement integration.
"""

from typing import Dict, List, Tuple, Any, Optional
import database
import notification


def get_active_tasks_and_matrices(db_path: Optional[str] = None) -> Tuple[
    List[str],                # Resource IDs
    Dict[str, int],           # Available vector {res: count}
    Dict[str, int],           # Total vector {res: count}
    Dict[int, Dict[str, Any]] # Active tasks metadata: {task_id: {user, role, email, status, priority, alloc, max, need, req}}
]:
    """
    Fetches the current state of resources and all active tasks (RUNNING, QUEUED, BLOCKED).
    Constructs the Available vector, Allocation matrix, Max matrix, and Need matrix.
    """
    resources_data = database.get_all_resources(db_path)
    res_ids = [r["resource_id"] for r in resources_data]
    available = {r["resource_id"]: r["available_instances"] for r in resources_data}
    total = {r["resource_id"]: r["total_instances"] for r in resources_data}

    all_tasks = database.get_all_tasks(db_path)
    all_allocs = database.get_all_allocations(db_path)

    # Group allocations by task_id
    task_allocs: Dict[int, Dict[str, Dict[str, int]]] = {}
    for a in all_allocs:
        tid = a["task_id"]
        if tid not in task_allocs:
            task_allocs[tid] = {}
        task_allocs[tid][a["resource_id"]] = {
            "allocated": a["allocated_units"],
            "requested": a["requested_units"],
            "max": a["max_demand"]
        }

    tasks_info: Dict[int, Dict[str, Any]] = {}
    for t in all_tasks:
        tid = t["task_id"]
        status = t["status"]
        if status in ("RUNNING", "QUEUED", "BLOCKED"):
            alloc_dict = {r: 0 for r in res_ids}
            max_dict = {r: 0 for r in res_ids}
            req_dict = {r: 0 for r in res_ids}
            need_dict = {r: 0 for r in res_ids}

            if tid in task_allocs:
                for r in res_ids:
                    if r in task_allocs[tid]:
                        alloc_val = task_allocs[tid][r]["allocated"]
                        max_val = task_allocs[tid][r]["max"]
                        req_val = task_allocs[tid][r]["requested"]
                        alloc_dict[r] = alloc_val
                        max_dict[r] = max_val
                        req_dict[r] = req_val
                        need_dict[r] = max(0, max_val - alloc_val)

            tasks_info[tid] = {
                "task_id": tid,
                "user_name": t["user_name"],
                "user_role": t.get("user_role", "Standard User"),
                "user_email": t.get("user_email", ""),
                "priority": t["priority"],
                "status": status,
                "created_at": t["created_at"],
                "allocation": alloc_dict,
                "max_demand": max_dict,
                "requested": req_dict,
                "need": need_dict
            }

    return res_ids, available, total, tasks_info


def check_banker_safety(
    candidate_task_id: int,
    request: Dict[str, int],
    db_path: Optional[str] = None
) -> Tuple[bool, List[int], str, List[str]]:
    """
    Executes Banker's Algorithm Safety State Check for a candidate task requesting resources.
    
    Returns:
      (is_safe: bool, safe_sequence: List[int], explanation: str, detailed_trace: List[str])
    """
    res_ids, available, total, tasks_info = get_active_tasks_and_matrices(db_path)

    if candidate_task_id not in tasks_info:
        return False, [], f"Candidate task #{candidate_task_id} not found among active tasks.", []

    cand_task = tasks_info[candidate_task_id]
    cand_name = cand_task["user_name"]
    cand_role = cand_task["user_role"]

    detailed_trace: List[str] = []
    detailed_trace.append(f"--- Banker's Safety Evaluation for Task #{candidate_task_id} ({cand_name} [{cand_role}]) ---")
    detailed_trace.append(f"Current Available: {available}")
    detailed_trace.append(f"Requested Allocation: {request}")

    # Step 1: Immediate Resource Availability Check
    for r in res_ids:
        req_val = request.get(r, 0)
        avail_val = available.get(r, 0)
        if req_val > avail_val:
            explanation = (
                f"Insufficient resources: Task #{candidate_task_id} ({cand_role}) requested {req_val} unit(s) of "
                f"'{r}', but only {avail_val} unit(s) are currently available."
            )
            detailed_trace.append(f"FAIL: Request exceeds available for '{r}' ({req_val} > {avail_val}).")
            return False, [], explanation, detailed_trace

    # Step 2: Pretend Allocation (Simulate State Transition)
    work = {r: available[r] - request.get(r, 0) for r in res_ids}
    
    # Active processes considered in safety check: All currently RUNNING tasks + Candidate Task
    running_task_ids = [tid for tid, info in tasks_info.items() if info["status"] == "RUNNING"]
    active_in_check = list(running_task_ids)
    if candidate_task_id not in active_in_check:
        active_in_check.append(candidate_task_id)

    # Calculate hypothetical Allocation' and Need' for active tasks
    sim_alloc: Dict[int, Dict[str, int]] = {}
    sim_need: Dict[int, Dict[str, int]] = {}

    for tid in active_in_check:
        t_info = tasks_info[tid]
        if tid == candidate_task_id:
            # Candidate receives the requested units
            sim_alloc[tid] = {r: t_info["allocation"][r] + request.get(r, 0) for r in res_ids}
            sim_need[tid] = {r: max(0, t_info["max_demand"][r] - sim_alloc[tid][r]) for r in res_ids}
        else:
            sim_alloc[tid] = dict(t_info["allocation"])
            sim_need[tid] = dict(t_info["need"])

    detailed_trace.append(f"Simulated Work vector after tentative allocation: {work}")
    detailed_trace.append(f"Active tasks participating in safety sequence: {active_in_check}")

    # Step 3: Safety State Algorithm (Find Safe Execution Sequence)
    finish = {tid: False for tid in active_in_check}
    safe_sequence: List[int] = []

    while True:
        found_executable = False
        for tid in active_in_check:
            if not finish[tid]:
                # Can this task finish with current Work vector?
                needs = sim_need[tid]
                can_finish = all(needs[r] <= work[r] for r in res_ids)
                if can_finish:
                    found_executable = True
                    finish[tid] = True
                    safe_sequence.append(tid)
                    t_user = tasks_info[tid]["user_name"]
                    t_role = tasks_info[tid]["user_role"]
                    
                    # Reclaim task's allocated resources back into Work
                    old_work = dict(work)
                    for r in res_ids:
                        work[r] += sim_alloc[tid][r]

                    detailed_trace.append(
                        f"Step {len(safe_sequence)}: Task #{tid} ({t_user} [{t_role}]) can finish! "
                        f"Need {needs} <= Work {old_work}. "
                        f"Reclaims {sim_alloc[tid]} -> New Work: {work}"
                    )
                    break  # Restart loop to evaluate remaining unfinished tasks

        if not found_executable:
            break

    # Step 4: Verification of Safe State
    is_safe = all(finish.values())
    if is_safe:
        seq_display = " -> ".join([f"T{tid} ({tasks_info[tid]['user_name']} [{tasks_info[tid]['user_role']}])" for tid in safe_sequence])
        explanation = f"Safe sequence found: [{seq_display}]. Allocation granted."
        detailed_trace.append(f"RESULT: System remains in SAFE STATE with sequence: [{seq_display}].")
        return True, safe_sequence, explanation, detailed_trace
    else:
        stuck_tasks = [
            f"T{tid} ({tasks_info[tid]['user_name']} [{tasks_info[tid]['user_role']}], Need: {sim_need[tid]})"
            for tid, fin in finish.items() if not fin
        ]
        explanation = (
            f"Safety check failed: Potential deadlock detected, task BLOCKED. "
            f"No safe sequence exists. Unfinished tasks unable to satisfy maximum demand with remaining Work {work}: "
            f"{', '.join(stuck_tasks)}."
        )
        detailed_trace.append(f"RESULT: System would enter UNSAFE STATE! Blocked tasks: {', '.join(stuck_tasks)}.")
        return False, [], explanation, detailed_trace


def evaluate_and_dispatch_task(
    task_id: int,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates a specific QUEUED or BLOCKED task using Banker's Algorithm.
    If SAFE: updates DB to mark as RUNNING and logs approval.
    If UNSAFE or INSUFFICIENT: updates DB to mark as BLOCKED and logs avoidance.
    """
    all_allocs = database.get_allocations_for_task(task_id, db_path)
    task_info = database.get_task(task_id, db_path)
    if not task_info:
        return {"success": False, "task_id": task_id, "message": "Task not found."}

    user_name = task_info["user_name"]
    user_role = task_info.get("user_role", "Standard User")

    # Determine requested units to start
    request_vector: Dict[str, int] = {}
    for a in all_allocs:
        res_id = a["resource_id"]
        req = a.get("requested_units", 0)
        alloc = a.get("allocated_units", 0)
        max_d = a.get("max_demand", 0)
        
        if req > 0:
            request_vector[res_id] = req
        else:
            request_vector[res_id] = max(0, max_d - alloc)

    # Execute safety check
    is_safe, safe_seq, explanation, trace = check_banker_safety(task_id, request_vector, db_path)

    if is_safe:
        database.mark_task_running(task_id, request_vector, db_path)
        database.add_safety_log(
            event_type="SAFETY_CHECK_PASSED",
            message=f"Task #{task_id} ('{user_name}' [{user_role}]) approved -> RUNNING.",
            details=explanation + "\n\n" + "\n".join(trace),
            task_id=task_id,
            db_path=db_path
        )
        return {
            "success": True,
            "status": "RUNNING",
            "task_id": task_id,
            "user_role": user_role,
            "message": explanation,
            "safe_sequence": safe_seq,
            "trace": trace
        }
    else:
        database.mark_task_blocked(task_id, db_path)
        database.add_safety_log(
            event_type="SAFETY_CHECK_FAILED",
            message=f"Task #{task_id} ('{user_name}' [{user_role}]) -> BLOCKED (Deadlock Avoidance).",
            details=explanation + "\n\n" + "\n".join(trace),
            task_id=task_id,
            db_path=db_path
        )
        return {
            "success": False,
            "status": "BLOCKED",
            "task_id": task_id,
            "user_role": user_role,
            "message": explanation,
            "safe_sequence": [],
            "trace": trace
        }


def dispatch_queue(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Priority & Boss Scheduling Dispatcher:
    Evaluates waiting tasks strictly ordered by:
      CASE WHEN user_role = 'Boss' THEN 0 ELSE 1 END,
      priority DESC,
      created_at ASC
    'Boss' tasks bypass lower-priority queues to achieve lowest waiting time.
    """
    all_tasks = database.get_all_tasks(db_path)
    waiting_tasks = [t for t in all_tasks if t["status"] in ("QUEUED", "BLOCKED")]

    # Explicit multi-level sort enforcing the Boss bypass rule
    waiting_tasks.sort(key=lambda t: (
        0 if t.get("user_role") == "Boss" else 1,
        -t["priority"],
        t["created_at"]
    ))

    dispatch_results: List[Dict[str, Any]] = []
    for t in waiting_tasks:
        result = evaluate_and_dispatch_task(t["task_id"], db_path)
        dispatch_results.append(result)

    return dispatch_results


def release_and_dispatch(
    task_id: int,
    smtp_config: Optional[Dict[str, Any]] = None,
    send_notification: bool = True,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Releases resources for a completed task, calculates billing settlement,
    dispatches email notification, and automatically re-evaluates all waiting
    tasks (BLOCKED and QUEUED) in priority order (with Boss bypass).
    """
    settlement = database.complete_task(task_id, db_path)
    
    notification_result = None
    if send_notification and settlement:
        email = settlement.get("user_email") or ""
        user = settlement.get("user_name", "User")
        amount = settlement.get("billing_amount", 0.0)
        duration = settlement.get("duration_seconds", 15)
        total_units = settlement.get("total_units", 0)

        notification_result = notification.dispatch_email_notification(
            user_email=email,
            user_name=user,
            task_id=task_id,
            amount=amount,
            smtp_config=smtp_config,
            duration_seconds=duration,
            total_units=total_units
        )
        # Log notification event into safety_logs
        database.add_safety_log(
            event_type="EMAIL_NOTIFICATION",
            message=f"Email alert dispatched for Task #{task_id} to {notification_result['email']}: {notification_result['status']}.",
            details=f"Subject: {notification_result['subject']}\nMode: {notification_result['mode']}\nmailto link: {notification_result['mailto_link']}\n\n{notification_result['body_text']}",
            task_id=task_id,
            db_path=db_path
        )

    dispatch_results = dispatch_queue(db_path)

    return {
        "task_id": task_id,
        "settlement": settlement,
        "notification": notification_result,
        "dispatched": dispatch_results
    }
