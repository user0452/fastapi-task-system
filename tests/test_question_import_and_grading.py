from app.modules.adaptive.grader import grade_response
from app.modules.adaptive.objective_tagger import align_question_to_objectives
from app.modules.adaptive.question_generator import validate_question
from app.modules.adaptive.question_import import (
    normalize_and_deduplicate,
    parse_question_bank,
)


def _objectives():
    return [
        {
            "id": 1,
            "title": "能够根据输入约束划分等价类",
            "description": "学生能够区分有效等价类和无效等价类并选择代表值。",
            "required_ability": "给定输入约束，说明类别边界和代表性测试输入。",
            "importance": 0.8,
        },
        {
            "id": 2,
            "title": "能够根据边界条件选择关键测试值",
            "description": "学生能够识别边界本身、边界附近和刚好越界的值。",
            "required_ability": "给定范围，列出边界及邻近测试值并说明理由。",
            "importance": 0.9,
        },
    ]


def test_question_import_supports_jsonl_markdown_and_all_question_types():
    json_payload = "\n".join(
        [
            '{"content":"选择正确的等价类代表值","question_type":"multiple_choice","options":["17","30","61"],"answer":"30"}',
            '{"content":"边界值分析是否关注刚好越界的值","question_type":"true_false","answer":"true"}',
            '{"content":"计算输入范围的有效值数量","question_type":"calculation","answer":"43","tolerance":0.5}',
            '{"content":"给定范围场景选择测试值","question_type":"scenario","answer":"覆盖边界场景"}',
            '{"content":"简述等价类划分的判断依据","question_type":"short_answer","answer":"按约束划分有效和无效类"}',
            '{"content":"论述边界值分析的覆盖理由","question_type":"essay","answer":"覆盖边界及其邻近区域"}',
        ]
    ).encode()
    parsed = parse_question_bank(json_payload, "bank.jsonl")

    assert [item.question_type for item in parsed] == [
        "multiple_choice",
        "true_false",
        "calculation",
        "scenario",
        "short_answer",
        "essay",
    ]
    assert parsed[0].options == ["17", "30", "61"]
    assert parsed[2].tolerance == 0.5
    assert parsed[0].raw_provenance["filename"] == "bank.jsonl"

    markdown = parse_question_bank(
        """题目：请说明边界值分析如何覆盖测试范围\n答案：覆盖最小值、最大值、邻近值和越界值\n\n题目：缺少答案的题目需要人工复核\n""".encode(),
        "bank.md",
    )
    assert markdown[0].parse_status == "ready"
    assert markdown[1].parse_status == "needs_review"

    deduped, duplicate_count = normalize_and_deduplicate(parsed + [parsed[0]])
    assert len(deduped) == 6
    assert duplicate_count == 1


def test_objective_tagger_only_returns_course_owned_ids_and_can_mark_unmatched():
    matched = align_question_to_objectives(
        "给定输入范围，请列出有效等价类、无效等价类和代表值。",
        "有效类覆盖约束范围，无效类覆盖小于下界和大于上界。",
        _objectives(),
    )
    assert matched["status"] == "matched"
    assert matched["alignments"]
    assert {item["objective_id"] for item in matched["alignments"]} <= {1, 2}

    unmatched = align_question_to_objectives(
        "请说明与课程无关的天气信息。",
        "天气变化。",
        _objectives(),
    )
    assert unmatched["status"] == "unmatched"
    assert unmatched["alignments"] == []


def test_deterministic_grader_handles_choices_boolean_calculation_and_open_misconception():
    choice = grade_response(
        {
            "question_type": "multiple_choice",
            "options": ["17", "30", "61"],
            "answer": "30",
        },
        "B",
    )
    assert choice["score"] == 1
    assert choice["grader_type"] == "deterministic-exact"

    truth = grade_response(
        {"question_type": "true_false", "answer": "true"},
        "错误",
    )
    assert truth["score"] == 0

    calculation = grade_response(
        {"question_type": "calculation", "answer": "43", "tolerance": 0.5},
        "43.4",
    )
    assert calculation["score"] == 1
    outside = grade_response(
        {"question_type": "calculation", "answer": "43", "tolerance": 0.5},
        "44",
    )
    assert outside["score"] == 0
    assert outside["misconception"]["code"] == "calculation_outside_tolerance"

    open_result = grade_response(
        {
            "question_type": "scenario",
            "answer": "需要说明边界条件和判断依据",
        },
        "不知道",
        objective=_objectives()[1],
    )
    assert open_result["score"] == 0
    assert open_result["misconception"]["code"] == "missing_key_evidence"
    assert open_result["grader_type"] == "deterministic-rubric-fallback"


def test_generated_question_validator_rejects_unscoped_or_duplicate_content():
    objective = _objectives()[0]
    duplicate = validate_question(
        {
            "content": "请解释“等价类”的核心概念。",
            "question_type": "short_answer",
            "answer": "按约束划分有效和无效类",
        },
        objective=objective,
        evidence_text="输入约束把输入域划分为有效等价类和无效等价类。",
    )
    assert not duplicate.valid

    valid = validate_question(
        {
            "content": "给定年龄范围 18 到 60，请列出边界附近的测试输入并说明等价类依据。",
            "question_type": "scenario",
            "answer": "测试 17、18、30、60、61，并说明有效类和无效类。",
        },
        objective=objective,
        evidence_text="输入约束把输入域划分为有效等价类和无效等价类，边界附近值需要单独覆盖。",
    )
    assert valid.valid
    assert valid.objective_alignment >= 0.45
