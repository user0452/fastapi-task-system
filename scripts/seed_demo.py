"""Seed the fixed Adaptive Tutor smoke course used by E2E and demos."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import get_settings
from app.core.database import get_cursor
from app.core.schema import upgrade_database
from app.core.test_database import validate_test_database_name
from app.integrations.file_storage import UPLOAD_ROOT
from app.modules.auth.passwords import hash_password

DEFAULT_PASSWORD = "A3Demo123!"
COURSE_NAME = "计算机网络 Mini Course"
MATERIAL_TITLE = "TCP 自适应学习讲义"
MATERIAL_CONTENT = """TCP 基础通信通过可靠传输、序号和确认机制保证数据按序到达。

流量控制关注接收端处理能力，接收窗口 rwnd 用来避免发送方超过接收端缓存能力。

拥塞控制关注网络路径承载能力，拥塞窗口 cwnd 用来避免发送方注入过多数据导致网络拥塞。rwnd 和 cwnd 共同约束实际发送窗口，但解决的问题不同。

慢启动阶段通常从较小的 cwnd 开始增长；当 cwnd 达到 ssthresh 后进入拥塞避免，窗口增长方式发生变化。给定 cwnd、ssthresh 和 ACK 状态，可以判断当前阶段。

拥塞避免阶段需要依据 ACK、丢包或超时等证据判断窗口变化，并区分网络拥塞信号与接收端能力限制。"""


def _embedding(seed: int) -> str:
    values = [((index + seed) % 17) + 1 for index in range(384)]
    norm = math.sqrt(sum(value * value for value in values))
    return json.dumps([round(value / norm, 8) for value in values])


def _insert_material(cursor, user_id: int, course_id: int) -> tuple[int, list[int]]:
    cursor.execute(
        """
        INSERT INTO course_materials
            (user_id, course_id, course_name, title, content, file_hash,
             parse_status, index_status, processing_status)
        VALUES (%s, %s, %s, %s, %s, %s, 'parsed', 'ready', 'ready')
        """,
        (
            user_id,
            course_id,
            COURSE_NAME,
            MATERIAL_TITLE,
            MATERIAL_CONTENT,
            hashlib.sha256(MATERIAL_CONTENT.encode("utf-8")).hexdigest(),
        ),
    )
    material_id = int(cursor.lastrowid)
    chunks = [
        "TCP 基础通过序号和确认机制提供可靠传输；流量控制关注接收端处理能力，rwnd 反映接收缓存约束。",
        "拥塞控制关注网络路径承载能力，cwnd 反映发送方针对网络拥塞的窗口。rwnd 与 cwnd 解决的问题不同。",
        "慢启动从较小 cwnd 开始增长，达到 ssthresh 后进入拥塞避免，窗口增长方式发生变化。",
        "ACK、丢包和超时是判断拥塞控制窗口变化的重要证据，需要与接收端 rwnd 限制区分。",
    ]
    chunk_ids: list[int] = []
    for index, chunk in enumerate(chunks):
        cursor.execute(
            """
            INSERT INTO course_material_chunks
                (user_id, material_id, course_name, chunk_index, chunk_text,
                 page_number, embedding_json, embedding_model, content_hash, indexed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s,
                    'mock-deterministic-384', %s, CURRENT_TIMESTAMP)
            """,
            (
                user_id,
                material_id,
                COURSE_NAME,
                index,
                chunk,
                index + 1,
                _embedding(index),
                hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
            ),
        )
        chunk_ids.append(int(cursor.lastrowid))
    return material_id, chunk_ids


def _insert_curriculum(cursor, user_id: int, course_id: int, material_id: int, chunk_ids: list[int]) -> list[int]:
    objective_specs = [
        (
            "能够解释 TCP 可靠传输的基本机制",
            "学生能够根据序号、确认和重传证据解释 TCP 如何提供可靠传输。",
            "给定 TCP 传输场景，指出序号和 ACK 如何支持可靠交付。",
            0.82,
            "medium",
            0,
        ),
        (
            "能够区分 TCP 流量控制与拥塞控制",
            "学生能够区分 rwnd 代表的接收端约束与 cwnd 代表的网络拥塞约束。",
            "给定窗口变化场景，判断它属于流量控制还是拥塞控制并说明依据。",
            0.98,
            "medium",
            1,
        ),
        (
            "能够解释 cwnd 与 rwnd 分别解决什么问题",
            "学生能够说明 cwnd 和 rwnd 的控制对象、证据来源和共同约束关系。",
            "给定发送窗口和接收窗口状态，解释实际发送上限由哪些因素决定。",
            0.94,
            "medium",
            1,
        ),
        (
            "能够根据 cwnd 和 ssthresh 判断 TCP 当前阶段",
            "学生能够依据 cwnd、ssthresh 和 ACK 状态判断慢启动或拥塞避免。",
            "给定 cwnd、ssthresh 和 ACK 状态，判断当前处于哪个阶段并说明理由。",
            0.90,
            "hard",
            2,
        ),
        (
            "能够解释拥塞避免中的窗口变化",
            "学生能够结合 ACK、丢包或超时证据判断拥塞避免阶段的窗口变化。",
            "给定连续 ACK 或丢包场景，判断拥塞窗口如何变化并区分接收端限制。",
            0.86,
            "hard",
            3,
        ),
    ]
    objective_ids: list[int] = []
    for title, description, ability, importance, difficulty, chunk_index in objective_specs:
        cursor.execute(
            """
            INSERT INTO learning_objectives
                (user_id, course_id, title, description, required_ability,
                 importance, difficulty, extraction_confidence, curriculum_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0.9600, 'demo-curriculum-v2')
            """,
            (user_id, course_id, title, description, ability, importance, difficulty),
        )
        objective_id = int(cursor.lastrowid)
        objective_ids.append(objective_id)
        cursor.execute(
            """
            INSERT INTO objective_evidence
                (user_id, course_id, objective_id, material_id, chunk_id, confidence)
            VALUES (%s, %s, %s, %s, %s, 0.9600)
            """,
            (user_id, course_id, objective_id, material_id, chunk_ids[chunk_index]),
        )

    relations = [
        (objective_ids[0], objective_ids[1], "TCP 基础机制是区分两个控制面的前置能力"),
        (objective_ids[1], objective_ids[2], "先区分控制目标，才能解释两个窗口的作用"),
        (objective_ids[1], objective_ids[3], "区分拥塞控制是判断 cwnd 阶段的前置能力"),
        (objective_ids[3], objective_ids[4], "先判断阶段，才能解释拥塞避免中的窗口变化"),
    ]
    for source_id, target_id, rationale in relations:
        cursor.execute(
            """
            INSERT INTO objective_relations
                (user_id, course_id, source_objective_id, target_objective_id,
                 relation_type, confidence, rationale)
            VALUES (%s, %s, %s, %s, 'prerequisite', 0.9000, %s)
            """,
            (user_id, course_id, source_id, target_id, rationale),
        )

    cursor.execute(
        """
        INSERT INTO curriculum_builds
            (user_id, course_id, material_id, status, extraction_confidence,
             model, prompt_version, completed_at)
        VALUES (%s, %s, %s, 'ready', 0.9600, 'demo-fixture',
                'objective-extraction-v2', CURRENT_TIMESTAMP(6))
        """,
        (user_id, course_id, material_id),
    )
    return objective_ids


def _insert_question_bank(cursor, user_id: int, course_id: int, material_id: int, objective_ids: list[int]) -> None:
    question_specs = [
        (
            "给定 TCP 传输场景，请说明序号和 ACK 如何共同支持可靠交付。",
            "序号标识数据顺序，ACK 确认已收到的数据，发送方可以据此发现丢失并重传。",
            "scenario",
            "medium",
            objective_ids[0],
        ),
        (
            "接收端缓存不足导致发送方降低发送速率，这属于流量控制还是拥塞控制？为什么？",
            "属于流量控制，因为 rwnd 反映接收端缓存和处理能力，而不是网络路径拥塞。",
            "scenario",
            "easy",
            objective_ids[1],
        ),
        (
            "网络出现拥塞信号但接收端缓存充足时，应该关注 cwnd 还是 rwnd？请说明理由。",
            "应该关注 cwnd，因为它限制发送方针对网络路径承载能力的注入速率。",
            "scenario",
            "medium",
            objective_ids[1],
        ),
        (
            "若 cwnd 小于 ssthresh 且 ACK 持续到达，TCP 通常处于什么阶段？",
            "处于慢启动阶段；cwnd 还没有达到 ssthresh。",
            "scenario",
            "medium",
            objective_ids[3],
        ),
        (
            "若 cwnd 已达到 ssthresh 且 ACK 持续到达，TCP 通常进入什么阶段？",
            "进入拥塞避免阶段，窗口增长方式相较慢启动变得更保守。",
            "scenario",
            "hard",
            objective_ids[3],
        ),
        (
            "拥塞避免阶段发生超时后，应该如何判断窗口变化的证据？",
            "应结合超时这一拥塞信号判断 cwnd 需要降低，并与 rwnd 的接收端限制区分。",
            "scenario",
            "hard",
            objective_ids[4],
        ),
    ]
    for content, answer, question_type, difficulty, objective_id in question_specs:
        cursor.execute(
            """
            INSERT INTO questions
                (user_id, course_id, content, question_type, answer, difficulty,
                 source_type, source_material_id, quality_score, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'textbook', %s, 0.9400, 'active')
            """,
            (user_id, course_id, content, question_type, answer, difficulty, material_id),
        )
        question_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO question_objectives
                (question_id, objective_id, relevance, coverage_type, confidence)
            VALUES (%s, %s, 0.9600, 'scenario', 0.9400)
            """,
            (question_id, objective_id),
        )


def _insert_student_model(cursor, user_id: int, course_id: int, objective_ids: list[int]) -> None:
    # The demo learner knows TCP basics, but has a concrete cwnd/rwnd
    # misconception. The first Next Action should therefore be repair.
    state_specs = [
        (objective_ids[0], 0.84, 0.82, 5, 5, 0, 4, 0, "mastered"),
        (objective_ids[1], 0.38, 0.54, 4, 1, 3, 0, 2, "learning"),
        (objective_ids[2], 0.0, 0.0, 0, 0, 0, 0, 0, "unknown"),
        (objective_ids[3], 0.0, 0.0, 0, 0, 0, 0, 0, "unknown"),
        (objective_ids[4], 0.0, 0.0, 0, 0, 0, 0, 0, "unknown"),
    ]
    for objective_id, mastery, confidence, attempts, correct, incorrect, success_streak, failure_streak, state in state_specs:
        cursor.execute(
            """
            INSERT INTO student_objective_states
                (user_id, course_id, objective_id, mastery, confidence,
                 attempt_count, correct_count, incorrect_count,
                 success_streak, failure_streak, state, model_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'bkt-inspired-v1')
            """,
            (user_id, course_id, objective_id, mastery, confidence, attempts, correct, incorrect, success_streak, failure_streak, state),
        )
    cursor.execute(
        """
        INSERT INTO misconceptions
            (user_id, course_id, objective_id, code, description, confidence, occurrence_count)
        VALUES (%s, %s, %s, 'confuse_cwnd_rwnd',
                '把接收端流量控制窗口 rwnd 与网络拥塞控制窗口 cwnd 混淆。', 0.8600, 2)
        """,
        (user_id, course_id, objective_ids[1]),
    )


def seed_user(username: str, password: str, reset: bool) -> dict[str, int | str]:
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        existing = cursor.fetchone()
        if existing and reset:
            cursor.execute("DELETE FROM users WHERE id = %s", (existing["id"],))
            existing = None
        if existing:
            raise RuntimeError(f"用户 {username} 已存在；使用 --reset 重新生成")

        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hash_password(password)),
        )
        user_id = int(cursor.lastrowid or 0)
        exam_at = datetime.now() + timedelta(days=7)
        cursor.execute(
            """
            INSERT INTO courses
                (user_id, name, goal, exam_at, daily_minutes, status, is_current)
            VALUES (%s, %s, '理解 TCP 控制机制并能完成场景判断', %s, 30,
                    'active', TRUE)
            """,
            (user_id, COURSE_NAME, exam_at),
        )
        course_id = int(cursor.lastrowid or 0)
        material_id, chunk_ids = _insert_material(cursor, user_id, course_id)
        objective_ids = _insert_curriculum(cursor, user_id, course_id, material_id, chunk_ids)
        _insert_question_bank(cursor, user_id, course_id, material_id, objective_ids)
        _insert_student_model(cursor, user_id, course_id, objective_ids)

    return {
        "username": username,
        "password": password,
        "user_id": user_id,
        "course_id": course_id,
        "material_id": material_id,
    }


def purge_users(username_prefix: str, *, require_test_database: bool = False) -> int:
    if require_test_database:
        validate_test_database_name(get_settings().database_name)
    prefix = username_prefix.strip()
    if len(prefix) < 3:
        raise ValueError("清理前缀至少需要 3 个字符")
    namespaced_prefix = f"{prefix}_"
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id FROM users WHERE username = %s OR LEFT(username, %s) = %s",
            (prefix, len(namespaced_prefix), namespaced_prefix),
        )
        user_ids = [int(row["id"]) for row in cursor.fetchall()]
        cursor.execute(
            "DELETE FROM users WHERE username = %s OR LEFT(username, %s) = %s",
            (prefix, len(namespaced_prefix), namespaced_prefix),
        )
        deleted = int(cursor.rowcount)

    upload_root = UPLOAD_ROOT.resolve()
    for user_id in user_ids:
        user_directory = (upload_root / str(user_id)).resolve()
        user_directory.relative_to(upload_root)
        if user_directory.is_dir():
            shutil.rmtree(user_directory)
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Adaptive Tutor 固定演示课程")
    parser.add_argument("--username-prefix", default="a3_demo")
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--purge-prefix", action="store_true")
    parser.add_argument(
        "--require-test-database",
        action="store_true",
        help="Reject cleanup unless DATABASE_NAME contains an explicit test marker.",
    )
    args = parser.parse_args()

    upgrade_database()
    purged_users = (
        purge_users(args.username_prefix, require_test_database=args.require_test_database)
        if args.purge_prefix
        else 0
    )
    results = []
    for index in range(args.count):
        username = args.username_prefix if args.count == 1 else f"{args.username_prefix}_{index}"
        results.append(seed_user(username, args.password, args.reset))
    print(json.dumps({"purged_users": purged_users, "users": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
