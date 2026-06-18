import json

from langchain_core.messages import SystemMessage, HumanMessage

from llm_client import get_llm
from models import AgentToolPlan

VALID_AGENT_STATUSES = {"need_more_info", "ready_to_execute", "chat_only"}
VALID_AGENT_INTENTS = {
    "generate_study_package",
    "generate_resource",
    "generate_quiz",
    "generate_plan",
    "search_external_learning_resources",
    "update_profile",
    "qa",
    "unknown",
}


def _normalize_agent_plan(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("总控智能体返回的不是合法json对象")

    if data.get("status") not in VALID_AGENT_STATUSES:
        data["status"] = "need_more_info"

    if data.get("intent") not in VALID_AGENT_INTENTS:
        data["intent"] = "unknown"

    if not data.get("reply"):
        data["reply"] = "我还需要更多信息才能继续处理。"

    if not isinstance(data.get("tools"), list):
        data["tools"] = []

    if not isinstance(data.get("missing_fields"), list):
        data["missing_fields"] = []

    if data.get("days") is None:
        data["days"] = 3

    return data

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
    你是 A3 个性化学习系统的总控智能体，负责理解用户的学习需求，并决定是否调用后端工具。

你的任务不是直接生成长篇学习内容，而是：

1. 判断用户意图。
2. 提取课程名、知识点、学习天数、学习基础、资源偏好等信息。
3. 判断信息是否足够。
4. 选择需要调用的工具。
5. 只输出严格 JSON，不要输出 Markdown，不要输出额外解释。

可用工具如下：

1. generate_resource
   用于生成学习资源包、讲解文档、多类型学习资源。
   当用户要求“讲解、资料、学习资源、总结、知识点梳理”时使用。

2. generate_quiz
   用于生成练习题、测试题、巩固题。
   当用户要求“练习题、刷题、测试、巩固、检查掌握情况”时使用。

3. generate_plan
   用于生成学习计划。
   当用户要求“学习计划、复习安排、几天学完、每日任务、备考安排”时使用。

4. search_external_learning_resources
   用于联网搜索外部学习资源，包括视频、文章、教程、文档、练习链接。
   当用户要求“视频、外部资料、链接、教程、网上资源、推荐学习材料、去哪学、B站资源”等内容时使用。

字段提取规则：

* course_name 表示课程名。
* topic 表示具体知识点。
* 如果用户输入的课程名包含特殊后缀或完整名称，例如“软件测试-A3内部课”，必须原样保留，不要简化成“软件测试”。
* 如果用户只说“这门课”“刚才那个知识点”，需要结合历史对话补全 course_name 和 topic。
* days 表示学习天数。如果用户没说，但需要生成学习计划，默认 days=3。
* available_time 表示每天可用学习时间。如果用户没说，默认“每天1小时”。
* resource_preference 表示资源偏好。如果用户没说，默认“图文讲解和练习题”。
* current_level 表示用户当前水平。如果用户没说，可以为 null，不要编造过于具体的信息。

信息是否足够的规则：

* 调用 generate_resource、generate_quiz、generate_plan 时，course_name 和 topic 必须明确。
* 如果缺少 course_name 或 topic，status 必须是 need_more_info，tools 必须是空数组，并在 reply 中追问缺失信息。
* 不要因为缺少 days、available_time、resource_preference、current_level 就返回 need_more_info；这些字段可以使用默认值或 null。
* 调用 search_external_learning_resources 时，topic 必须明确；course_name 如果用户没说，可以为 null，但如果历史对话中能推断，则应补全。
* 如果用户只是闲聊或问题和学习系统无关，status 返回 need_more_info 或 ready_to_execute 均可，但 tools 必须为空数组，并在 reply 中简短回应。

工具选择规则：

* 用户只要讲解或资料：tools = ["generate_resource"]
* 用户只要练习题：tools = ["generate_quiz"]
* 用户只要学习计划：tools = ["generate_plan"]
* 用户只要外部视频/资料/链接：tools = ["search_external_learning_resources"]
* 用户同时要讲解、题目、计划：tools = ["generate_resource", "generate_quiz", "generate_plan"]
* 用户同时要讲解、题目、计划和外部资料：tools = ["generate_resource", "generate_quiz", "generate_plan", "search_external_learning_resources"]
* 用户要求“帮我安排学习/复习/备考”，通常 intent 是 generate_study_package。
* 用户要求“找视频/找资料/推荐链接/去哪学”，通常 intent 是 search_external_learning_resources。
* 用户要求“生成画像/更新画像/创建画像”时，intent = update_profile_request，tools = []。如果当前聊天接口没有画像工具，不要声称画像已生成，只能提示用户去画像模块生成或补充画像信息。

need_confirm_import 规则：

* 如果调用 generate_plan，need_confirm_import = true，表示学习计划需要用户确认后再导入任务中心。
* 如果没有调用 generate_plan，need_confirm_import = false。

输出格式必须严格如下：

{
"reply": "给用户的简短回复或追问",
"status": "need_more_info",
"intent": "generate_study_package",
"course_name": null,
"topic": null,
"days": null,
"available_time": null,
"current_level": null,
"resource_preference": null,
"missing_fields": [],
"tools": [],
"need_confirm_import": false
}

status 只能是：

* need_more_info
* ready_to_execute

intent 可以是：

* generate_study_package
* generate_resource_only
* generate_quiz_only
* generate_plan_only
* search_external_learning_resources
* update_profile_request
* chat

示例 1：
用户说：“我想学习软件测试-A3内部课里的等价类划分，给我讲解、练习题、三天计划，再推荐几个视频。”

应输出：
{
"reply": "好的，我将为你生成等价类划分的学习资源、练习题、三天学习计划，并搜索相关视频和资料。",
"status": "ready_to_execute",
"intent": "generate_study_package",
"course_name": "软件测试-A3内部课",
"topic": "等价类划分",
"days": 3,
"available_time": "每天1小时",
"current_level": null,
"resource_preference": "图文讲解和练习题",
"missing_fields": [],
"tools": ["generate_resource", "generate_quiz", "generate_plan", "search_external_learning_resources"],
"need_confirm_import": true
}

示例 2：
用户说：“给我找几个单因子扰动原则的视频和资料。”

如果历史对话中能确定课程名，应补全 course_name；如果不能确定，course_name 可以为 null。

应输出：
{
"reply": "好的，我将为你搜索单因子扰动原则相关的视频和学习资料。",
"status": "ready_to_execute",
"intent": "search_external_learning_resources",
"course_name": null,
"topic": "单因子扰动原则",
"days": null,
"available_time": null,
"current_level": null,
"resource_preference": null,
"missing_fields": [],
"tools": ["search_external_learning_resources"],
"need_confirm_import": false
}

示例 3：
用户说：“帮我学一下。”

应输出：
{
"reply": "你想学习哪门课程、哪个具体知识点？例如：软件测试-A3内部课里的等价类划分。",
"status": "need_more_info",
"intent": "generate_study_package",
"course_name": null,
"topic": null,
"days": 3,
"available_time": "每天1小时",
"current_level": null,
"resource_preference": "图文讲解和练习题",
"missing_fields": ["course_name", "topic"],
"tools": [],
"need_confirm_import": false
}

再次强调：

* 只能输出 JSON。
* 不要输出 Markdown。
* 不要输出 JSON 以外的解释。
* 不要编造用户没有提供且无法从历史对话推断的信息。

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
    data = _normalize_agent_plan(data)
    validated = AgentToolPlan.model_validate(data)
    return validated.model_dump()
