"""
Factory Task Generator — Default initial task generator & task helper.
"""

from typing import Dict
from flo.core.models import TaskModel, TaskPriority, TaskStatus

def get_initial_tasks() -> Dict[str, TaskModel]:
    raw_tasks = [
        ("T001", "WAREHOUSE", "M1", TaskPriority.NORMAL, 15.0, 300.0),
        ("T002", "WAREHOUSE", "M2", TaskPriority.NORMAL, 20.0, 300.0),
        ("T003", "M1", "ASSY", TaskPriority.HIGH, 25.0, 240.0),
        ("T004", "M2", "ASSY", TaskPriority.NORMAL, 20.0, 300.0),
        ("T005", "ASSY", "DISPATCH", TaskPriority.NORMAL, 35.0, 180.0),
    ]

    tasks = {}
    for tid, pickup, dest, prio, weight, deadline in raw_tasks:
        tasks[tid] = TaskModel(
            task_id=tid,
            pickup=pickup,
            destination=dest,
            priority=prio,
            weight=weight,
            deadline_seconds=deadline,
            status=TaskStatus.WAITING
        )
    return tasks
