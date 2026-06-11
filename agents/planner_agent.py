import json

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from llm_client import get_llm
from models import LearningPlan

def generate_learning_plan(
        course_name: str,
        topic: str,
        days: int,
        profile: dict | None = None
)->dict:
    llm = get_llm()
    profile_text = json.dumps(profile) if profile else "无"
    messages = [
        SystemMessage(
            content=(
                "你是一个个性化学习计划生成助手。\n"
                "请根据课程名、知识点、计划天数和学生画像，生成一份学习计划预览。\n"
                "必须严格围绕用户提供的课程名和知识点生成计划。\n"
                "学生画像只用于调整任务难度、任务数量、学习节奏和表达方式，不能改变课程主题。\n"
                "你必须只返回 JSON，不要返回解释文字，不要使用 Markdown。\n"
                "返回格式必须严格如下：\n"
                "{\n"
                '  "plan_title": "计划标题",\n'
                '  "course_name": "课程名",\n'
                '  "topic": "知识点",\n'
                '  "days": 3,\n'
                '  "tasks_preview": [\n'
                "    {\n"
                '      "title": "任务标题",\n'
                '      "description": "任务描述",\n'
                '      "status": "todo",\n'
                '      "priority": "low/medium/high"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "status 固定为 todo。\n"
                "priority 只能是 low、medium、high。\n"
                "tasks_preview 中每个任务都应该可以直接写入任务表。\n"
                "任务数量根据 days 合理生成，一般每天 1 到 3 个任务。\n"
                "不要生成空泛任务，比如“好好复习”“认真学习”。"
            )
        ),
        HumanMessage(
            content=(
                f"课程名：{course_name}\n"
                f"知识点：{topic}\n"
                f"计划天数：{days}\n"
                f"学生画像：{profile_text}"
            )
        )
    ]
    result = llm.invoke(messages)
    content = result.content.strip()

    try:
        data = json.loads(content)
        plan = LearningPlan.model_validate( data)
        return plan.model_dump()
    except json.JSONDecodeError as e:
        raise ValueError(f"模型返回的json格式错误：{content}")
    except ValidationError as e:
        raise ValueError(f"学习计划字段校验失败：{e}")

if __name__ == "__main__":
    test_profile = {
        "grade": "大三",
        "major": "软件工程",
        "goals": ["期末复习", "实习准备"],
        "weaknesses": ["软件测试", "测试用例设计"],
        "available_time": "每天2小时",
        "learning_preference": "喜欢任务拆解和例题"
    }

    print(
        generate_learning_plan(
            course_name="软件测试",
            topic="等价类划分",
            days=3,
            profile=test_profile
        )
    )