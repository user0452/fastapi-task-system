import json

from langchain_core.messages import SystemMessage, HumanMessage

from llm_client import get_llm
from models import AgentToolPlan

def analyze_user_learning_request(
        message:str,
        profile:dict | None = None,
        history: list[dict] | None = None
)->dict:
    """
        总控智能体第一版：
        只负责理解用户自然语言学习需求，并规划需要调用哪些工具。
        暂时不直接执行工具。
    """
    history_text = json.dumps(history or [],ensure_ascii=False)
    llm = get_llm()
    system_prompt = """
    你是总控智能体，需要通过多轮对话收集学习需求。

你必须判断当前信息是否足够调用工具。

如果缺少课程名或知识点，不允许调用 generate_resource/generate_quiz/generate_plan，status 必须是 need_more_info，并在 reply 中主动追问。

如果用户要求制定学习计划，但没有说明天数或每天可用时间，可以追问；如果用户表达“随便安排/你决定”，可以默认 days=3。

如果信息足够，status 为 ready_to_execute，并给出 tools。

你必须结合历史对话理解用户补充的信息。

JSON 格式如下：
{
  "reply": "还需要补充的信息或执行前说明",
  "status": "need_more_info",
  "intent": "generate_study_package",
  "course_name": "软件测试",
  "topic": null,
  "days": null,
  "available_time": null,
  "current_level": null,
  "resource_preference": null,
  "missing_fields": ["topic", "days"],
  "tools": [],
  "need_confirm_import": true
}
信息足够后才能返回：
{
  "reply": "好的，我将为你生成等价类划分的学习资源、练习题和三天学习计划。",
  "status": "ready_to_execute",
  "intent": "generate_study_package",
  "course_name": "软件测试",
  "topic": "等价类划分",
  "days": 3,
  "available_time": "每天2小时",
  "current_level": "基础薄弱",
  "resource_preference": "图文讲解和练习题",
  "missing_fields": [],
  "tools": ["generate_resource", "generate_quiz", "generate_plan"],
  "need_confirm_import": true
}

规则：
- 如果用户想“帮我安排学习/复习/备考”，通常 intent 是 generate_study_package。
- 如果用户同时需要资源、题目、计划，tools 包含 generate_resource、generate_quiz、generate_plan。
- 如果用户只想要讲解资料，tools 只包含 generate_resource。
- 如果用户只想刷题，tools 只包含 generate_quiz。
- 如果用户只想制定计划，tools 只包含 generate_plan。
- 如果用户输入包含“几天/三天/一周”等，提取为 days；没有则默认 3。
- 如果课程名或知识点不明确，course_name/topic 可以为 null，并在 reply 中提醒用户补充。
- 不允许编造过于具体的信息。
"""
    profile_text = json.dumps( profile,ensure_ascii= False) if profile else "暂无学生画像"
    human_prompt = f"""
当前学生画像:{profile_text}
最近对话历史:{history_text}
用户输入:{message}
"""
    result = llm.invoke(
        [SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)]
    )
    content = result.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("总控智能体返回的不是合法json")
    validated = AgentToolPlan.model_validate(data)
    return validated.model_dump()
