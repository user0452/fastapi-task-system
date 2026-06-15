import json

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from llm_client import get_llm
from models import LearningEvaluationResult


def evaluate_quiz_answers(
        quiz_set_id: int,
        quiz_title: str,
        questions: list[dict],
        user_answers: list[dict],
        profile: dict | None = None
) -> dict:
    """
    学习效果评估智能体：
    根据题目、参考答案和用户答案，评估用户掌握情况。
    """
    if not user_answers:
        raise ValueError("用户答案不能为空")

    answer_map = {
        item["question_id"]: item["user_answer"]
        for item in user_answers
    }

    evaluation_items = []

    for question in questions:
        question_id = question["id"]

        if question_id not in answer_map:
            continue

        evaluation_items.append(
            {
                "question_id": question_id,
                "question": question["question"],
                "reference_answer": question["answer"],
                "question_type": question["question_type"],
                "difficulty": question["difficulty"],
                "user_answer": answer_map[question_id]
            }
        )

    if not evaluation_items:
        raise ValueError("没有找到可评估的题目答案")

    llm = get_llm()

    profile_text = json.dumps(profile, ensure_ascii=False) if profile else "暂无学生画像"
    evaluation_text = json.dumps(evaluation_items, ensure_ascii=False)

    messages = [
        SystemMessage(
            content=(
                "你是一个学习效果评估智能体。\n"
                "你需要根据题目、参考答案、用户答案和学生画像，评估学生对知识点的掌握情况。\n"
                "评分时不要机械匹配文字，而要判断语义是否正确。\n"
                "如果用户答案表达不完整，但核心意思正确，可以给较高分。\n"
                "如果用户答案概念混淆、遗漏关键点或无法解释原因，应扣分。\n"
                "你必须只返回 JSON，不要返回解释文字，不要使用 Markdown。\n"
                "返回格式必须严格如下：\n"
                "{\n"
                '  "quiz_set_id": 1,\n'
                '  "score": 85,\n'
                '  "level": "掌握较好",\n'
                '  "summary": "整体评价",\n'
                '  "weak_points": ["薄弱点1", "薄弱点2"],\n'
                '  "suggestions": ["建议1", "建议2"],\n'
                '  "question_reviews": [\n'
                "    {\n"
                '      "question_id": 1,\n'
                '      "question": "题目内容",\n'
                '      "reference_answer": "参考答案",\n'
                '      "user_answer": "用户答案",\n'
                '      "score": 80,\n'
                '      "feedback": "本题反馈",\n'
                '      "weak_point": "本题暴露的薄弱点或 null"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "score 必须是 0 到 100 的整数。\n"
                "总分 score 应综合所有题目的得分给出。\n"
                "level 可以是：掌握很好、掌握较好、基本掌握、需要复习。\n"
                "weak_points 和 suggestions 不存在时返回空数组 []。"
            )
        ),
        HumanMessage(
            content=(
                f"题集 ID：{quiz_set_id}\n"
                f"题集标题：{quiz_title}\n"
                f"学生画像：{profile_text}\n"
                f"待评估答案：{evaluation_text}"
            )
        )
    ]

    result = llm.invoke(messages)
    content = result.content.strip()

    try:
        data = json.loads(content)
        data["quiz_set_id"] = quiz_set_id
        evaluation = LearningEvaluationResult.model_validate(data)
        return evaluation.model_dump()
    except json.JSONDecodeError:
        raise ValueError(f"模型返回的json格式错误：{content}")
    except ValidationError as e:
        raise ValueError(f"学习效果评估字段校验失败：{e}")