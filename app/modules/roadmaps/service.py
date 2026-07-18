from __future__ import annotations

from datetime import date, datetime
from math import floor

from app.core.database import get_cursor
from app.core.errors import AppError
from app.core.time_utils import utc_naive_to_local
from app.modules.account.service import get_user_local_date, get_user_timezone
from app.modules.audit.service import record_audit
from app.modules.courses import repository as course_repository
from app.modules.roadmaps import repository


def _target_date(user_id: int, course: dict) -> date | None:
    value = course.get("exam_at")
    if value is None:
        return None
    if isinstance(value, datetime):
        return utc_naive_to_local(value, get_user_timezone(user_id)).date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


STAGE_SHARES = (0.15, 0.4, 0.3, 0.15)


def _allocate_stage_days(total_days: int) -> list[int]:
    total_days = max(1, int(total_days))
    stage_count = len(STAGE_SHARES)
    if total_days < stage_count:
        return [1 if position < total_days else 0 for position in range(stage_count)]

    days = [1] * stage_count
    remaining = total_days - stage_count
    quotas = [remaining * share / sum(STAGE_SHARES) for share in STAGE_SHARES]
    allocated = [floor(quota) for quota in quotas]
    for index, value in enumerate(allocated):
        days[index] += value
    leftover = remaining - sum(allocated)
    priority = sorted(
        range(stage_count),
        key=lambda index: (-(quotas[index] - allocated[index]), index),
    )
    for index in priority[:leftover]:
        days[index] += 1
    if sum(days) != total_days:
        raise RuntimeError("路线阶段天数分配失败")
    return days


def _stage_days(user_id: int, target_date: date | None) -> list[int]:
    today = get_user_local_date(user_id)
    total_days = max(1, (target_date - today).days) if target_date else 28
    return _allocate_stage_days(total_days)


def _stage_specs(user_id: int, course: dict) -> list[dict]:
    target_date = _target_date(user_id, course)
    days = _stage_days(user_id, target_date)
    name = str(course.get("name") or "本课程")
    goal = str(course.get("goal") or f"系统掌握{name}")
    daily_minutes = int(course.get("daily_minutes") or 30)
    return [
        {
            "position": 1,
            "name": "目标定标与基础诊断",
            "goal": f"围绕“{goal}”建立真实起点，识别已掌握内容与薄弱项。",
            "status": "active",
            "progress": 0,
            "estimated_days": days[0],
            "completion_condition": "完成课程资料准备与入门诊断，形成首份掌握度记录。",
            "recommended_content": ["补充课程资料", "完成入门诊断", "核对学习目标与目标日期"],
            "adaptation_reason": "依据课程创建时填写的目标生成；尚未使用诊断成绩。",
        },
        {
            "position": 2,
            "name": "核心知识构建",
            "goal": f"以每天约 {daily_minutes} 分钟学习节奏，建立{name}的核心知识结构。",
            "status": "pending",
            "progress": 0,
            "estimated_days": days[1],
            "completion_condition": "路线关联知识点的平均掌握度达到 70%。",
            "recommended_content": ["按知识关系学习先修内容", "用课程资料形成笔记", "对薄弱知识点提问"],
            "adaptation_reason": "上传资料后会关联真实知识点，诊断完成后会更新进度与优先级。",
        },
        {
            "position": 3,
            "name": "刻意练习与错题修复",
            "goal": "通过每日学习单元和针对性练习，把薄弱知识转化为稳定能力。",
            "status": "pending",
            "progress": 0,
            "estimated_days": days[2],
            "completion_condition": "核心知识平均掌握度达到 80%，并完成计划中的重点练习。",
            "recommended_content": ["执行每日计划", "提交练习并查看反馈", "回顾错题与调整原因"],
            "adaptation_reason": "每日单元会在诊断生成计划后自动关联到本阶段。",
        },
        {
            "position": 4,
            "name": "综合检验与目标冲刺",
            "goal": f"综合运用所学内容，验证是否达到“{goal}”。",
            "status": "pending",
            "progress": 0,
            "estimated_days": days[3],
            "completion_condition": "核心知识点达到目标掌握度，且综合练习结果稳定。",
            "recommended_content": ["完成综合练习", "集中复盘剩余薄弱项", "按目标日期安排最后冲刺"],
            "adaptation_reason": "进入条件由真实掌握度与练习结果决定。",
        },
    ]


def _generate(
    cursor,
    roadmap: dict,
    course: dict,
    *,
    idempotency_key: str,
    attempt: int,
) -> dict:
    job = repository.create_generation_job(
        cursor,
        roadmap,
        idempotency_key,
        attempt,
    )
    if job["status"] == "ready":
        return roadmap
    repository.mark_generation_started(cursor, roadmap["id"], job["id"])
    try:
        repository.replace_stages(
            cursor,
            roadmap,
            _stage_specs(roadmap["user_id"], course),
        )
        repository.mark_generation_ready(cursor, roadmap["id"], job["id"])
    except Exception as exc:
        repository.mark_generation_failed(cursor, roadmap["id"], job["id"], str(exc))
    refreshed = repository.get_roadmap(
        cursor,
        roadmap["user_id"],
        roadmap["course_id"],
    )
    if refreshed is None:
        raise RuntimeError("路线图生成后无法读取")
    return refreshed


def initialize_course_roadmap(cursor, user_id: int, course: dict) -> dict:
    locked_course = course_repository.get_course_for_update(
        cursor,
        course["id"],
        user_id,
    )
    if locked_course is None:
        raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
    course = locked_course
    roadmap = repository.get_roadmap(cursor, user_id, course["id"], for_update=True)
    if roadmap is None:
        roadmap = repository.create_roadmap(
            cursor,
            user_id,
            course,
            _target_date(user_id, course),
        )
    if roadmap["status"] == "pending":
        roadmap = _generate(
            cursor,
            roadmap,
            course,
            idempotency_key=f"initial:{course['id']}:v1",
            attempt=1,
        )
    return roadmap


def _sync_links(cursor, roadmap: dict) -> None:
    if roadmap.get("status") != "ready":
        return
    repository.sync_point_links(cursor, roadmap)
    repository.sync_session_links(cursor, roadmap)


def sync_course_links(user_id: int, course_id: int) -> None:
    with get_cursor() as cursor:
        roadmap = repository.get_roadmap(cursor, user_id, course_id)
        if roadmap is not None:
            _sync_links(cursor, roadmap)


def get_learning_roadmap(user_id: int, course_id: int) -> dict:
    with get_cursor() as cursor:
        course = course_repository.get_course(cursor, course_id, user_id)
        if course is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        roadmap = initialize_course_roadmap(cursor, user_id, course)
        _sync_links(cursor, roadmap)
        result = repository.get_details(cursor, roadmap)
        result["overall_progress"] = calculate_overall_progress(
            result["stages"],
            int(roadmap.get("daily_minutes") or 30),
        )
        record_audit(
            user_id,
            "LEARNING_ROADMAP_VIEWED",
            "learning_roadmap",
            roadmap["id"],
            {"course_id": course_id, "status": roadmap["status"]},
            cursor=cursor,
        )
        return result


def retry_learning_roadmap(user_id: int, course_id: int, reason: str) -> dict:
    with get_cursor() as cursor:
        course = course_repository.get_course(cursor, course_id, user_id)
        if course is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        roadmap = initialize_course_roadmap(cursor, user_id, course)
        if roadmap["status"] != "failed":
            raise AppError("只有生成失败的路线图可以重试", 409, "ROADMAP_RETRY_NOT_ALLOWED")
        next_version = int(roadmap["version"] or 1) + 1
        cursor.execute(
            "UPDATE learning_roadmaps SET version = %s WHERE id = %s",
            (next_version, roadmap["id"]),
        )
        roadmap["version"] = next_version
        roadmap = _generate(
            cursor,
            roadmap,
            course,
            idempotency_key=f"retry:{roadmap['id']}:v{next_version}",
            attempt=next_version,
        )
        record_audit(
            user_id,
            "LEARNING_ROADMAP_RETRIED",
            "learning_roadmap",
            roadmap["id"],
            {"course_id": course_id, "reason": reason, "version": next_version},
            cursor=cursor,
        )
        result = repository.get_details(cursor, roadmap)
        result["overall_progress"] = calculate_overall_progress(
            result["stages"],
            int(roadmap.get("daily_minutes") or 30),
        )
        return result


def attach_summaries(cursor, user_id: int, courses: list[dict]) -> list[dict]:
    for course in courses:
        initialize_course_roadmap(cursor, user_id, course)
    summaries = repository.summaries_for_courses(
        cursor,
        user_id,
        [course["id"] for course in courses],
    )
    progress_inputs = repository.progress_inputs_for_roadmaps(
        cursor,
        [summary["id"] for summary in summaries.values()],
    )
    for course in courses:
        summary = summaries.get(course["id"])
        if summary is not None:
            summary["overall_progress"] = calculate_overall_progress(
                progress_inputs.get(summary["id"], []),
                int(course.get("daily_minutes") or 30),
            )
        course["roadmap_summary"] = summary
    return courses


def attach_summary(cursor, user_id: int, course: dict) -> dict:
    return attach_summaries(cursor, user_id, [course])[0]


def refresh_course_snapshot(
    cursor,
    user_id: int,
    course: dict,
    changed_fields: set[str],
    previous_course: dict | None = None,
) -> None:
    roadmap = initialize_course_roadmap(cursor, user_id, course)
    course_with_target = {
        **course,
        "roadmap_target_date": _target_date(user_id, course),
    }
    repository.update_course_snapshot(cursor, roadmap["id"], course_with_target)
    relevant = changed_fields & {"goal", "exam_at", "daily_minutes"}
    if not relevant:
        return
    reason = "课程设置已更新：" + "、".join(sorted(relevant))
    key = f"course-update:{course['id']}:{course.get('updated_at')}:{','.join(sorted(relevant))}"
    current_stages = repository.stage_map(cursor, roadmap["id"])
    next_stages = _stage_specs(user_id, course)
    before = {
        "goal": (previous_course or {}).get("goal", roadmap.get("goal_snapshot") or ""),
        "target_date": roadmap.get("target_date"),
        "daily_minutes": (previous_course or {}).get(
            "daily_minutes",
            roadmap.get("daily_minutes") or 30,
        ),
        "stages": [
            {
                "position": stage["position"],
                "status": stage["status"],
                "progress": stage["progress"],
                "estimated_days": stage["estimated_days"],
            }
            for stage in current_stages.values()
        ],
    }
    for spec in next_stages:
        stage = current_stages.get(spec["position"])
        if stage is None:
            raise RuntimeError(f"路线缺少第 {spec['position']} 阶段")
        repository.update_stage_blueprint(
            cursor,
            stage,
            spec,
            adaptation_reason=f"{reason}；{spec['adaptation_reason']}",
        )
    after = {
        "goal": course.get("goal") or "",
        "target_date": course_with_target["roadmap_target_date"],
        "daily_minutes": course.get("daily_minutes") or 30,
        "stages": [
            {
                "position": spec["position"],
                "status": current_stages[spec["position"]]["status"],
                "progress": current_stages[spec["position"]]["progress"],
                "estimated_days": spec["estimated_days"],
            }
            for spec in next_stages
        ],
    }
    repository.create_adjustment(
        cursor,
        roadmap,
        trigger_type="course_update",
        trigger_id=course["id"],
        idempotency_key=key,
        reason=reason,
        details={"changed_fields": sorted(relevant), "before": before, "after": after},
    )
    repository.touch_adjusted(cursor, roadmap["id"])


def calculate_overall_progress(stages: list[dict], daily_minutes: int = 30) -> float:
    if not stages:
        return 0.0
    weighted_total = 0.0
    total_weight = 0.0
    minutes_per_day = max(1, int(daily_minutes or 30))
    for stage in stages:
        progress = max(0.0, min(float(stage.get("progress") or 0), 100.0))
        if "unit_minutes" in stage:
            unit_minutes = max(0.0, float(stage.get("unit_minutes") or 0))
        else:
            unit_minutes = sum(
                max(0.0, float(item.get("estimated_minutes") or 0))
                for item in (stage.get("daily_sessions") or [])
            )
        estimated_days = max(0, int(stage.get("estimated_days") or 0))
        weight = unit_minutes or estimated_days * minutes_per_day
        if weight <= 0:
            continue
        weighted_total += progress * weight
        total_weight += weight
    if total_weight <= 0:
        return round(
            sum(max(0.0, min(float(stage.get("progress") or 0), 100.0)) for stage in stages)
            / len(stages),
            2,
        )
    return round(max(0.0, min(weighted_total / total_weight, 100.0)), 2)


def _mastery_average(stage: dict | None) -> float:
    points = (stage or {}).get("knowledge_points") or []
    if not points:
        return 0.0
    return sum(float(point.get("mastery") or 0) for point in points) / len(points)


def adjust_roadmap_for_evaluation(
    cursor,
    *,
    user_id: int,
    course_id: int,
    trigger_type: str,
    trigger_id: int,
    evaluation: dict,
    mastery_changes: list[dict],
) -> bool:
    roadmap = repository.get_roadmap(cursor, user_id, course_id, for_update=True)
    if roadmap is None or roadmap["status"] != "ready":
        return False
    _sync_links(cursor, roadmap)
    score = float(evaluation.get("score") or 0)
    weakest = sorted(
        mastery_changes,
        key=lambda item: float(
            item.get("new_mastery")
            or item.get("after")
            or item.get("mastery")
            or 0
        ),
    )[:3]
    weak_ids = [item.get("knowledge_point_id") for item in weakest]
    reason = (
        f"{trigger_type} 结果为 {score:.0f} 分；"
        + (f"优先巩固知识点 {', '.join(map(str, weak_ids))}。" if weak_ids else "按现有掌握度继续推进。")
    )
    idempotency_key = f"{trigger_type}:{trigger_id}"
    created = repository.create_adjustment(
        cursor,
        roadmap,
        trigger_type=trigger_type,
        trigger_id=trigger_id,
        idempotency_key=idempotency_key,
        reason=reason,
        details={
            "score": score,
            "knowledge_point_ids": weak_ids,
            "mastery_change_count": len(mastery_changes),
        },
    )
    if not created:
        return False

    stages = repository.stage_map(cursor, roadmap["id"])
    core_average = _mastery_average(stages.get(2))
    practice_progress = min(100.0, core_average * 0.7 + score * 0.3)

    if 1 in stages:
        repository.update_stage(
            cursor,
            stages[1]["id"],
            status="completed",
            progress=100,
            adaptation_reason="已完成真实诊断或学习评估，学习起点已记录。",
        )
    if 2 in stages:
        repository.update_stage(
            cursor,
            stages[2]["id"],
            status="completed" if core_average >= 70 else "active",
            progress=core_average,
            adaptation_reason=reason,
        )
    if 3 in stages:
        if core_average >= 80 and practice_progress >= 80:
            practice_status = "completed"
        elif trigger_type == "diagnostic" and core_average < 70:
            practice_status = "pending"
        else:
            practice_status = "active"
        repository.update_stage(
            cursor,
            stages[3]["id"],
            status=practice_status,
            progress=practice_progress if practice_status != "pending" else 0,
            adaptation_reason=reason,
        )
    if 4 in stages:
        ready_for_sprint = core_average >= 80 and practice_progress >= 80
        sprint_progress = max(0.0, min(100.0, (core_average + score) / 2 - 20))
        repository.update_stage(
            cursor,
            stages[4]["id"],
            status="active" if ready_for_sprint else "pending",
            progress=sprint_progress if ready_for_sprint else 0,
            adaptation_reason=(
                "核心知识与练习指标已达到冲刺入口。"
                if ready_for_sprint
                else "待核心知识平均掌握度和练习表现均达到 80%。"
            ),
        )
    repository.touch_adjusted(cursor, roadmap["id"])
    return True
