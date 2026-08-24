# ruff: noqa: E402

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
from utils import hash_password

DEFAULT_PASSWORD = "A3Demo123!"
MATERIAL_CONTENT = """等价类划分把输入域划分为有效等价类和无效等价类，从每类选择代表值设计测试用例。
有效等价类满足需求约束，无效等价类违反一个明确约束。每个有效类至少覆盖一次，无效类通常单独设计用例。

边界值分析关注输入范围边界以及边界附近的值。通常覆盖最小值、略高于最小值、正常值、略低于最大值、最大值和刚好越界的值。

判定表适合多个条件组合产生不同动作的规则。先列条件桩和动作桩，再枚举规则列，消除不可能组合并把有效规则转成测试用例。"""


def _embedding(seed: int) -> str:
    values = [((index + seed) % 17) + 1 for index in range(384)]
    norm = math.sqrt(sum(value * value for value in values))
    return json.dumps([round(value / norm, 8) for value in values])


def seed_user(username: str, password: str, reset: bool) -> dict:
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
        user_id = cursor.lastrowid
        exam_at = datetime.now().replace(second=0, microsecond=0) + timedelta(days=7)
        cursor.execute(
            """
            INSERT INTO courses
                (user_id, name, goal, exam_at, daily_minutes, status, is_current)
            VALUES (%s, '软件测试冲刺', '七天掌握测试设计核心方法', %s, 30,
                    'diagnostic_pending', TRUE)
            """,
            (user_id, exam_at),
        )
        course_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO course_materials
                (user_id, course_id, course_name, title, content, file_hash,
                 parse_status, index_status, processing_status)
            VALUES (%s, %s, '软件测试冲刺', '软件测试设计方法讲义', %s, %s,
                    'parsed', 'ready', 'ready')
            """,
            (
                user_id,
                course_id,
                MATERIAL_CONTENT,
                hashlib.sha256(MATERIAL_CONTENT.encode("utf-8")).hexdigest(),
            ),
        )
        material_id = cursor.lastrowid

        chunks = [
            "等价类划分把输入域分成有效类和无效类，每类选择代表值。边界值分析覆盖边界、边界附近值以及刚好越界的值。",
            "判定表由条件桩、动作桩、条件项和动作项构成，每条有效规则转换为测试用例。",
        ]
        chunk_ids = []
        for index, chunk in enumerate(chunks):
            cursor.execute(
                """
                INSERT INTO course_material_chunks
                    (user_id, material_id, course_name, chunk_index, chunk_text,
                     page_number, embedding_json, embedding_model, content_hash, indexed_at)
                VALUES (%s, %s, '软件测试冲刺', %s, %s, %s, %s,
                        'mock-deterministic-384', %s, CURRENT_TIMESTAMP)
                """,
                (
                    user_id,
                    material_id,
                    index,
                    chunk,
                    index + 1,
                    _embedding(index),
                    hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                ),
            )
            chunk_ids.append(cursor.lastrowid)

        point_specs = [
            (
                "等价类划分",
                "将输入域划分为有效类和无效类。",
                "从每一类选择代表值设计测试用例。",
                "年龄允许 18 到 60 时，17、30、61 分属不同等价类。",
                [chunk_ids[0]],
            ),
            (
                "边界值分析",
                "覆盖边界、边界附近以及越界输入。",
                "优先检查边界本身和刚好越界的值。",
                "长度要求 11 位时测试 10、11、12 位输入。",
                [chunk_ids[0]],
            ),
            (
                "判定表",
                "系统覆盖多个条件的有效组合。",
                "把每条有效规则转换成测试用例。",
                "会员等级和订单金额共同决定折扣时列出条件组合。",
                [chunk_ids[1]],
            ),
        ]
        points = []
        for order, (name, description, summary, example, sources) in enumerate(point_specs):
            vector_text = (
                f"名称：{name}\n定义：{description}\n摘要：{summary}\n例子：{example}"
            )
            cursor.execute(
                """
                INSERT INTO knowledge_points
                    (user_id, course_id, name, description, summary, examples_json,
                     source_chunk_ids, sort_order, embedding_json, embedding_model, embedding_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'mock-deterministic-384', %s)
                """,
                (
                    user_id,
                    course_id,
                    name,
                    description,
                    summary,
                    json.dumps([example], ensure_ascii=False),
                    json.dumps(sources),
                    order,
                    _embedding(order + 10),
                    hashlib.sha256(vector_text.encode("utf-8")).hexdigest(),
                ),
            )
            points.append(
                {
                    "id": cursor.lastrowid,
                    "name": name,
                    "description": description,
                    "summary": summary,
                    "examples": [example],
                }
            )

        for source, target in zip(points, points[1:]):
            cursor.execute(
                """
                INSERT INTO knowledge_point_relations
                    (user_id, course_id, source_point_id, target_point_id,
                     relation_type, confidence)
                VALUES (%s, %s, %s, %s, 'prerequisite', 0.8000)
                """,
                (user_id, course_id, source["id"], target["id"]),
            )

        # Adaptive Tutor demo data is deliberately separate from the legacy
        # knowledge-point/quiz tables.  The seeded learner has a concrete
        # misconception so the first action demonstrates repair instead of a
        # generic chat or a fixed roadmap.
        objective_specs = [
            (
                "能够使用等价类划分设计有效与无效输入",
                "学生能够依据输入约束划分有效类和无效类，并为每一类选择代表值。",
                "给定输入约束，说明类别边界并设计代表性测试输入。",
                0.78,
                "medium",
                0,
            ),
            (
                "能够根据边界条件选择关键测试值",
                "学生能够识别最小值、最大值、边界附近值和刚好越界值，并说明覆盖理由。",
                "给定一个输入范围，列出边界及其邻近测试值并解释选择。",
                0.92,
                "medium",
                0,
            ),
            (
                "能够把判定表规则转换为测试用例",
                "学生能够从条件桩和动作桩枚举有效规则，排除不可能组合并形成测试用例。",
                "给定多个条件和动作，判断有效规则并写出预期结果。",
                0.86,
                "hard",
                1,
            ),
        ]
        adaptive_objectives = []
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
            objective_id = cursor.lastrowid
            adaptive_objectives.append(objective_id)
            cursor.execute(
                """
                INSERT INTO objective_evidence
                    (user_id, course_id, objective_id, material_id, chunk_id, confidence)
                VALUES (%s, %s, %s, %s, %s, 0.9600)
                """,
                (user_id, course_id, objective_id, material_id, chunk_ids[chunk_index]),
            )

        for source_id, target_id, rationale in [
            (adaptive_objectives[0], adaptive_objectives[1], "等价类边界是选择边界测试值的前置能力"),
            (adaptive_objectives[1], adaptive_objectives[2], "边界条件判断有助于检查判定表规则覆盖"),
        ]:
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

        question_specs = [
            (
                "年龄允许 18 到 60 岁时，请列出等价类并为每类给出一个代表值。",
                "有效等价类是 18 到 60，代表值可以是 30；无效等价类是小于 18 和大于 60，代表值可以是 17 和 61。",
                "easy",
                adaptive_objectives[0],
            ),
            (
                "输入长度要求为 11 位时，应优先检查哪些边界值？请说明理由。",
                "应检查 10、11、12 位，分别覆盖刚好低于下界、边界本身和刚好高于上界的情况。",
                "medium",
                adaptive_objectives[1],
            ),
            (
                "会员等级为普通或金牌，订单金额大于 100 才有折扣。请说明至少两条有效规则及预期动作。",
                "需要组合会员等级和订单金额两个条件；例如普通且金额不大于 100 无折扣，金牌且金额大于 100 有折扣。",
                "hard",
                adaptive_objectives[2],
            ),
        ]
        for content, answer, difficulty, objective_id in question_specs:
            cursor.execute(
                """
                INSERT INTO questions
                    (user_id, course_id, content, question_type, answer, difficulty,
                     source_type, source_material_id, quality_score, status)
                VALUES (%s, %s, %s, 'short_answer', %s, %s,
                        'textbook', %s, 0.9400, 'active')
                """,
                (user_id, course_id, content, answer, difficulty, material_id),
            )
            question_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO question_objectives
                    (question_id, objective_id, relevance, coverage_type, confidence)
                VALUES (%s, %s, 0.9600, 'scenario', 0.9400)
                """,
                (question_id, objective_id),
            )

        # Objective 1 is recently validated; Objective 2 is the useful next
        # target and carries the seeded confusion for the smoke scenario.
        state_specs = [
            (adaptive_objectives[0], 0.82, 0.78, 4, 4, 0, 4, 0, "mastered"),
            (adaptive_objectives[1], 0.38, 0.54, 3, 1, 2, 0, 2, "learning"),
            (adaptive_objectives[2], 0.0, 0.0, 0, 0, 0, 0, 0, "unknown"),
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
                (user_id, course_id, objective_id, mastery, confidence, attempts, correct,
                 incorrect, success_streak, failure_streak, state),
            )
        cursor.execute(
            """
            INSERT INTO misconceptions
                (user_id, course_id, objective_id, code, description, confidence,
                 occurrence_count)
            VALUES (%s, %s, %s, 'boundary_value_selection',
                    '容易把边界本身与刚好越界的测试值混为一谈。', 0.8200, 2)
            """,
            (user_id, course_id, adaptive_objectives[1]),
        )

        cursor.execute(
            """
            INSERT INTO quiz_sets
                (user_id, course_id, title, course_name, topic, quiz_json, purpose)
            VALUES (%s, %s, '软件测试冲刺入门诊断', '软件测试冲刺', '课程诊断',
                    '{"questions":[]}', 'diagnostic')
            """,
            (user_id, course_id),
        )
        quiz_id = cursor.lastrowid
        for index in range(6):
            point = points[index % len(points)]
            cursor.execute(
                """
                INSERT INTO quiz_questions
                    (quiz_set_id, knowledge_point_id, question_type,
                     question, answer, difficulty)
                VALUES (%s, %s, 'short_answer', %s, %s, 'medium')
                """,
                (
                    quiz_id,
                    point["id"],
                    f"请说明{point['name']}的核心方法与一个应用场景（{index + 1}）。",
                    point["description"],
                ),
            )

        cursor.execute(
            """
            INSERT INTO student_profiles (user_id, profile_json)
            VALUES (%s, %s)
            """,
            (
                user_id,
                json.dumps(
                    {
                        "learning_stage": "课程冲刺",
                        "learning_goal": "按每日计划完成软件测试复习",
                    },
                    ensure_ascii=False,
                ),
            ),
        )

        cursor.execute(
            """
            INSERT INTO chat_sessions (user_id, course_id, title)
            VALUES (%s, %s, '软件测试冲刺学习对话')
            """,
            (user_id, course_id),
        )
        session_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO course_agents
                (user_id, course_id, name, status, primary_session_id, last_active_at)
            VALUES (%s, %s, '软件测试冲刺 学习助手', 'active', %s, CURRENT_TIMESTAMP)
            """,
            (user_id, course_id, session_id),
        )

    return {
        "username": username,
        "password": password,
        "user_id": user_id,
        "course_id": course_id,
        "material_id": material_id,
        "quiz_id": quiz_id,
        "session_id": session_id,
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
        user_ids = [row["id"] for row in cursor.fetchall()]
        cursor.execute(
            "DELETE FROM users WHERE username = %s OR LEFT(username, %s) = %s",
            (prefix, len(namespaced_prefix), namespaced_prefix),
        )
        deleted = cursor.rowcount

    upload_root = UPLOAD_ROOT.resolve()
    for user_id in user_ids:
        user_directory = (upload_root / str(user_id)).resolve()
        user_directory.relative_to(upload_root)
        if user_directory.is_dir():
            shutil.rmtree(user_directory)
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 A3 比赛演示数据")
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
        purge_users(
            args.username_prefix,
            require_test_database=args.require_test_database,
        )
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
