from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def _json(value: Any, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _number(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


def get_roadmap(
    cursor,
    user_id: int,
    course_id: int,
    *,
    for_update: bool = False,
) -> dict | None:
    lock = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT * FROM learning_roadmaps
        WHERE user_id = %s AND course_id = %s{lock}
        """,
        (user_id, course_id),
    )
    return cursor.fetchone()


def create_roadmap(cursor, user_id: int, course: dict, target_date) -> dict:
    cursor.execute(
        """
        INSERT IGNORE INTO learning_roadmaps
            (user_id, course_id, status, generation_method, goal_snapshot,
             target_date, daily_minutes)
        VALUES (%s, %s, 'pending', 'rules_v1', %s, %s, %s)
        """,
        (
            user_id,
            course["id"],
            course.get("goal") or "",
            target_date,
            course.get("daily_minutes") or 30,
        ),
    )
    roadmap = get_roadmap(cursor, user_id, course["id"], for_update=True)
    if roadmap is None:
        raise RuntimeError("路线图创建后无法读取")
    return roadmap


def create_generation_job(
    cursor,
    roadmap: dict,
    idempotency_key: str,
    attempt: int,
) -> dict:
    cursor.execute(
        """
        INSERT IGNORE INTO roadmap_generation_jobs
            (roadmap_id, user_id, course_id, idempotency_key, status, attempt)
        VALUES (%s, %s, %s, %s, 'pending', %s)
        """,
        (
            roadmap["id"],
            roadmap["user_id"],
            roadmap["course_id"],
            idempotency_key,
            attempt,
        ),
    )
    cursor.execute(
        """
        SELECT * FROM roadmap_generation_jobs
        WHERE user_id = %s AND idempotency_key = %s
        """,
        (roadmap["user_id"], idempotency_key),
    )
    job = cursor.fetchone()
    if job is None:
        raise RuntimeError("路线图生成任务创建后无法读取")
    return job


def mark_generation_started(cursor, roadmap_id: int, job_id: int) -> None:
    cursor.execute(
        """
        UPDATE roadmap_generation_jobs
        SET status = 'generating', started_at = UTC_TIMESTAMP(),
            completed_at = NULL, error_message = NULL
        WHERE id = %s AND roadmap_id = %s
        """,
        (job_id, roadmap_id),
    )
    cursor.execute(
        """
        UPDATE learning_roadmaps
        SET status = 'generating', last_error = NULL
        WHERE id = %s
        """,
        (roadmap_id,),
    )


def replace_stages(cursor, roadmap: dict, stages: list[dict]) -> None:
    cursor.execute(
        "DELETE FROM learning_roadmap_stages WHERE roadmap_id = %s",
        (roadmap["id"],),
    )
    for stage in stages:
        cursor.execute(
            """
            INSERT INTO learning_roadmap_stages
                (roadmap_id, user_id, course_id, position, name, goal, status,
                 progress, estimated_days, completion_condition,
                 recommended_content_json, adaptation_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                roadmap["id"],
                roadmap["user_id"],
                roadmap["course_id"],
                stage["position"],
                stage["name"],
                stage["goal"],
                stage["status"],
                stage["progress"],
                stage["estimated_days"],
                stage["completion_condition"],
                json.dumps(stage["recommended_content"], ensure_ascii=False),
                stage.get("adaptation_reason"),
            ),
        )


def mark_generation_ready(cursor, roadmap_id: int, job_id: int) -> None:
    cursor.execute(
        """
        UPDATE roadmap_generation_jobs
        SET status = 'ready', completed_at = UTC_TIMESTAMP(), error_message = NULL
        WHERE id = %s AND roadmap_id = %s
        """,
        (job_id, roadmap_id),
    )
    cursor.execute(
        """
        UPDATE learning_roadmaps
        SET status = 'ready', generated_at = UTC_TIMESTAMP(), last_error = NULL
        WHERE id = %s
        """,
        (roadmap_id,),
    )


def mark_generation_failed(cursor, roadmap_id: int, job_id: int, error: str) -> None:
    message = error[:2000]
    cursor.execute(
        """
        UPDATE roadmap_generation_jobs
        SET status = 'failed', completed_at = UTC_TIMESTAMP(), error_message = %s
        WHERE id = %s AND roadmap_id = %s
        """,
        (message, job_id, roadmap_id),
    )
    cursor.execute(
        """
        UPDATE learning_roadmaps
        SET status = 'failed', last_error = %s
        WHERE id = %s
        """,
        (message, roadmap_id),
    )


def latest_job(cursor, roadmap_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT * FROM roadmap_generation_jobs
        WHERE roadmap_id = %s
        ORDER BY id DESC LIMIT 1
        """,
        (roadmap_id,),
    )
    return cursor.fetchone()


def list_stages(cursor, roadmap_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT * FROM learning_roadmap_stages
        WHERE roadmap_id = %s ORDER BY position ASC
        """,
        (roadmap_id,),
    )
    stages = list(cursor.fetchall())
    for stage in stages:
        stage["progress"] = _number(stage.get("progress"))
        stage["recommended_content"] = _json(
            stage.pop("recommended_content_json", None), []
        )
        cursor.execute(
            """
            SELECT kp.id, kp.name, kp.description, rsp.sort_order,
                   rsp.required_mastery, COALESCE(mr.mastery, 0) AS mastery
            FROM roadmap_stage_points rsp
            JOIN knowledge_points kp ON kp.id = rsp.knowledge_point_id
            LEFT JOIN mastery_records mr
              ON mr.user_id = rsp.user_id
             AND mr.course_id = rsp.course_id
             AND mr.knowledge_point_id = rsp.knowledge_point_id
            WHERE rsp.stage_id = %s
            ORDER BY rsp.sort_order ASC, kp.id ASC
            """,
            (stage["id"],),
        )
        points = list(cursor.fetchall())
        for point in points:
            point["required_mastery"] = _number(point.get("required_mastery"))
            point["mastery"] = _number(point.get("mastery"))
        stage["knowledge_points"] = points
        cursor.execute(
            """
            SELECT ss.id, ss.scheduled_date, ss.status, ss.estimated_minutes,
                   rss.link_reason
            FROM roadmap_stage_sessions rss
            JOIN study_sessions ss ON ss.id = rss.study_session_id
            WHERE rss.stage_id = %s
            ORDER BY ss.scheduled_date ASC, ss.id ASC
            """,
            (stage["id"],),
        )
        stage["daily_sessions"] = list(cursor.fetchall())
    return stages


def list_adjustments(cursor, roadmap_id: int, limit: int = 20) -> list[dict]:
    cursor.execute(
        """
        SELECT id, trigger_type, trigger_id, reason, details_json, created_at
        FROM roadmap_adjustments
        WHERE roadmap_id = %s
        ORDER BY id DESC LIMIT %s
        """,
        (roadmap_id, limit),
    )
    adjustments = list(cursor.fetchall())
    for item in adjustments:
        item["details"] = _json(item.pop("details_json", None), {})
    return adjustments


def get_details(cursor, roadmap: dict) -> dict:
    result = dict(roadmap)
    result["stages"] = list_stages(cursor, roadmap["id"])
    result["generation_job"] = latest_job(cursor, roadmap["id"])
    result["adjustments"] = list_adjustments(cursor, roadmap["id"])
    return result


def stage_map(cursor, roadmap_id: int) -> dict[int, dict]:
    return {stage["position"]: stage for stage in list_stages(cursor, roadmap_id)}


def sync_point_links(cursor, roadmap: dict) -> None:
    stages = stage_map(cursor, roadmap["id"])
    target_stages = [stages[position] for position in (2, 3) if position in stages]
    if not target_stages:
        return
    cursor.execute(
        """
        SELECT id, sort_order FROM knowledge_points
        WHERE user_id = %s AND course_id = %s AND status = 'active'
        ORDER BY sort_order ASC, id ASC
        """,
        (roadmap["user_id"], roadmap["course_id"]),
    )
    points = list(cursor.fetchall())
    for stage in target_stages:
        required = 70 if stage["position"] == 2 else 80
        for index, point in enumerate(points):
            cursor.execute(
                """
                INSERT IGNORE INTO roadmap_stage_points
                    (stage_id, knowledge_point_id, user_id, course_id,
                     sort_order, required_mastery)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    stage["id"],
                    point["id"],
                    roadmap["user_id"],
                    roadmap["course_id"],
                    point.get("sort_order") or index,
                    required,
                ),
            )


def sync_session_links(cursor, roadmap: dict) -> None:
    stages = stage_map(cursor, roadmap["id"])
    stage = stages.get(3)
    if stage is None:
        return
    cursor.execute(
        """
        SELECT ss.id
        FROM study_sessions ss
        JOIN study_plans sp ON sp.id = ss.plan_id
        WHERE ss.user_id = %s AND ss.course_id = %s
          AND sp.user_id = %s AND sp.course_id = %s
        ORDER BY ss.scheduled_date ASC, ss.id ASC
        """,
        (
            roadmap["user_id"],
            roadmap["course_id"],
            roadmap["user_id"],
            roadmap["course_id"],
        ),
    )
    for session in cursor.fetchall():
        cursor.execute(
            """
            INSERT IGNORE INTO roadmap_stage_sessions
                (stage_id, study_session_id, user_id, course_id, link_reason)
            VALUES (%s, %s, %s, %s, 'daily_plan')
            """,
            (
                stage["id"],
                session["id"],
                roadmap["user_id"],
                roadmap["course_id"],
            ),
        )


def create_adjustment(
    cursor,
    roadmap: dict,
    *,
    trigger_type: str,
    trigger_id: int | None,
    idempotency_key: str,
    reason: str,
    details: dict,
) -> bool:
    cursor.execute(
        """
        INSERT IGNORE INTO roadmap_adjustments
            (roadmap_id, user_id, course_id, trigger_type, trigger_id,
             idempotency_key, reason, details_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            roadmap["id"],
            roadmap["user_id"],
            roadmap["course_id"],
            trigger_type,
            trigger_id,
            idempotency_key,
            reason[:500],
            json.dumps(details, ensure_ascii=False, default=str),
        ),
    )
    return cursor.rowcount == 1


def update_stage(
    cursor,
    stage_id: int,
    *,
    status: str,
    progress: float,
    adaptation_reason: str | None,
) -> None:
    cursor.execute(
        """
        UPDATE learning_roadmap_stages
        SET status = %s, progress = %s, adaptation_reason = %s
        WHERE id = %s
        """,
        (status, round(max(0, min(progress, 100)), 2), adaptation_reason, stage_id),
    )


def update_stage_blueprint(
    cursor,
    stage: dict,
    spec: dict,
    *,
    adaptation_reason: str,
) -> None:
    if stage.get("status") == "completed":
        cursor.execute(
            "UPDATE learning_roadmap_stages SET estimated_days = %s WHERE id = %s",
            (spec["estimated_days"], stage["id"]),
        )
        return
    cursor.execute(
        """
        UPDATE learning_roadmap_stages
        SET name = %s, goal = %s, estimated_days = %s,
            completion_condition = %s, recommended_content_json = %s,
            adaptation_reason = %s
        WHERE id = %s
        """,
        (
            spec["name"],
            spec["goal"],
            spec["estimated_days"],
            spec["completion_condition"],
            json.dumps(spec["recommended_content"], ensure_ascii=False),
            adaptation_reason[:500],
            stage["id"],
        ),
    )


def touch_adjusted(cursor, roadmap_id: int) -> None:
    cursor.execute(
        """
        UPDATE learning_roadmaps
        SET last_adjusted_at = UTC_TIMESTAMP()
        WHERE id = %s
        """,
        (roadmap_id,),
    )


def update_course_snapshot(cursor, roadmap_id: int, course: dict) -> None:
    cursor.execute(
        """
        UPDATE learning_roadmaps
        SET goal_snapshot = %s, target_date = %s, daily_minutes = %s
        WHERE id = %s
        """,
        (
            course.get("goal") or "",
            course.get("roadmap_target_date"),
            course.get("daily_minutes") or 30,
            roadmap_id,
        ),
    )


def summaries_for_courses(
    cursor,
    user_id: int,
    course_ids: list[int],
) -> dict[int, dict]:
    if not course_ids:
        return {}
    placeholders = ",".join(["%s"] * len(course_ids))
    cursor.execute(
        f"""
        SELECT lr.id, lr.course_id, lr.status, lr.last_error,
               lrs.name AS current_stage_name, lrs.progress AS current_stage_progress,
               lrs.position AS current_stage_position,
               (SELECT COUNT(*) FROM learning_roadmap_stages all_stages
                WHERE all_stages.roadmap_id = lr.id) AS stage_total
        FROM learning_roadmaps lr
        LEFT JOIN learning_roadmap_stages lrs
          ON lrs.roadmap_id = lr.id
         AND lrs.position = (
             SELECT MIN(candidate.position)
             FROM learning_roadmap_stages candidate
             WHERE candidate.roadmap_id = lr.id AND candidate.status <> 'completed'
         )
        WHERE lr.user_id = %s AND lr.course_id IN ({placeholders})
        FOR UPDATE
        """,
        (user_id, *course_ids),
    )
    summaries = {}
    for row in cursor.fetchall():
        if row.get("current_stage_progress") is not None:
            row["current_stage_progress"] = _number(row["current_stage_progress"])
        summaries[row["course_id"]] = row
    return summaries


def progress_inputs_for_roadmaps(cursor, roadmap_ids: list[int]) -> dict[int, list[dict]]:
    if not roadmap_ids:
        return {}
    placeholders = ",".join(["%s"] * len(roadmap_ids))
    cursor.execute(
        f"""
        SELECT stage.roadmap_id, stage.progress, stage.estimated_days,
               COALESCE(SUM(session.estimated_minutes), 0) AS unit_minutes
        FROM learning_roadmap_stages stage
        LEFT JOIN roadmap_stage_sessions link ON link.stage_id = stage.id
        LEFT JOIN study_sessions session ON session.id = link.study_session_id
        WHERE stage.roadmap_id IN ({placeholders})
        GROUP BY stage.id, stage.roadmap_id, stage.progress, stage.estimated_days
        ORDER BY stage.roadmap_id ASC, stage.position ASC
        """,
        tuple(roadmap_ids),
    )
    grouped: dict[int, list[dict]] = {}
    for row in cursor.fetchall():
        row["progress"] = _number(row.get("progress"))
        row["unit_minutes"] = _number(row.get("unit_minutes"))
        grouped.setdefault(row["roadmap_id"], []).append(row)
    return grouped
