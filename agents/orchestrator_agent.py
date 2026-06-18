import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from llm_client import get_llm
from models import AgentToolPlan

VALID_AGENT_STATUSES = {"need_more_info", "ready_to_execute", "chat_only"}

VALID_AGENT_INTENTS = {
    "generate_study_package",
    "generate_resource",
    "generate_resource_only",
    "list_resources",
    "get_resource",
    "generate_quiz",
    "generate_quiz_only",
    "list_quizzes",
    "get_quiz",
    "generate_plan",
    "generate_plan_only",
    "import_plan_tasks",
    "search_external_learning_resources",
    "generate_profile",
    "get_profile",
    "update_profile",
    "update_profile_request",
    "create_material",
    "list_materials",
    "build_material_index",
    "rag_search_materials",
    "create_task",
    "list_tasks",
    "get_task",
    "update_task",
    "delete_task",
    "bulk_update_tasks_status",
    "bulk_delete_tasks_status",
    "submit_evaluation",
    "list_evaluations",
    "get_evaluation",
    "parse_exam_schedule",
    "preview_review_plan",
    "import_review_plan_tasks",
    "list_operation_logs",
    "qa",
    "chat",
    "unknown",
}

VALID_AGENT_TOOLS = {
    "generate_profile",
    "get_profile",
    "create_material",
    "list_materials",
    "build_material_index",
    "rag_search_materials",
    "generate_resource",
    "list_resources",
    "get_resource",
    "generate_quiz",
    "list_quizzes",
    "get_quiz",
    "generate_plan",
    "import_plan_tasks",
    "search_external_learning_resources",
    "create_task",
    "list_tasks",
    "get_task",
    "update_task",
    "delete_task",
    "bulk_update_tasks_status",
    "bulk_delete_tasks_status",
    "submit_evaluation",
    "list_evaluations",
    "get_evaluation",
    "parse_exam_schedule",
    "preview_review_plan",
    "import_review_plan_tasks",
    "list_operation_logs",
}

INTENT_ALIASES = {
}

TOOL_ALIASES = {
    "generate_resource_only": "generate_resource",
    "generate_quiz_only": "generate_quiz",
    "generate_plan_only": "generate_plan",
    "update_profile": "generate_profile",
    "update_profile_request": "generate_profile",
    "search_external_resources": "search_external_learning_resources",
    "list_material": "list_materials",
    "list_resource": "list_resources",
    "list_quiz": "list_quizzes",
    "list_task": "list_tasks",
    "list_evaluation": "list_evaluations",
    "list_logs": "list_operation_logs",
}

CHINESE_NUMBER_MAP = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
}


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _normalize_tools(tools: object) -> list[str]:
    if not isinstance(tools, list):
        return []

    normalized = []
    for tool in tools:
        if not isinstance(tool, str):
            continue
        name = TOOL_ALIASES.get(tool, tool)
        if name in VALID_AGENT_TOOLS and name not in normalized:
            normalized.append(name)
    return normalized


def _normalize_agent_plan(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("总控智能体返回的不是合法json对象")

    if data.get("status") not in VALID_AGENT_STATUSES:
        data["status"] = "need_more_info"

    data["intent"] = INTENT_ALIASES.get(data.get("intent"), data.get("intent"))
    if data.get("intent") not in VALID_AGENT_INTENTS:
        data["intent"] = "unknown"

    if not data.get("reply"):
        data["reply"] = "我还需要更多信息才能继续处理。"

    data["tools"] = _normalize_tools(data.get("tools"))

    if not isinstance(data.get("missing_fields"), list):
        data["missing_fields"] = []

    if data.get("days") is None:
        data["days"] = 3

    if not isinstance(data.get("tool_args"), dict):
        data["tool_args"] = {}

    for tool_name in list(data["tool_args"].keys()):
        normalized_name = TOOL_ALIASES.get(tool_name, tool_name)
        if normalized_name != tool_name:
            data["tool_args"][normalized_name] = data["tool_args"].pop(tool_name)

    if "generate_plan" in data["tools"] and "need_confirm_import" not in data:
        data["need_confirm_import"] = True

    return data


def _extract_days_from_message(message: str) -> int | None:
    digit_match = re.search(r"(\d+)\s*天", message)
    if digit_match:
        return int(digit_match.group(1))

    chinese_match = re.search(r"([一二两三四五六七])\s*天", message)
    if chinese_match:
        return CHINESE_NUMBER_MAP.get(chinese_match.group(1))

    return None


def _apply_rule_based_fallback(data: dict, message: str) -> dict:
    """
    兜底处理比赛演示中常见的“学习 X 里的 Y”表达，避免模型偶发漏抽取。
    """
    if data.get("status") != "need_more_info" and data.get("tools"):
        return data

    match = re.search(
        r"(?:学习|复习|掌握)(?P<course>.+?)(?:里的|里|中的|中)(?P<topic>[^，。,.、]+)",
        message
    )
    if not match:
        return data

    course_name = match.group("course").strip()
    topic = match.group("topic").strip()

    if not course_name or not topic:
        return data

    tools = []
    if any(word in message for word in ["讲解", "资料", "资源", "总结", "梳理"]):
        tools.append("generate_resource")
    if any(word in message for word in ["练习题", "题集", "刷题", "测试题", "巩固"]):
        tools.append("generate_quiz")
    if any(word in message for word in ["计划", "安排", "任务"]):
        tools.append("generate_plan")
    if any(word in message for word in ["视频", "外部", "网上", "链接", "推荐", "文章", "文档"]):
        tools.append("search_external_learning_resources")

    if not tools:
        return data

    data["status"] = "ready_to_execute"
    data["intent"] = "generate_study_package" if len(tools) > 1 else tools[0]
    data["course_name"] = data.get("course_name") or course_name
    data["topic"] = data.get("topic") or topic
    data["days"] = _extract_days_from_message(message) or data.get("days") or 3
    data["available_time"] = data.get("available_time") or "每天1小时"
    data["resource_preference"] = data.get("resource_preference") or "图文讲解和练习题"
    data["missing_fields"] = []
    data["tools"] = tools
    data["need_confirm_import"] = "generate_plan" in tools

    if not data.get("reply") or "补充" in data.get("reply", ""):
        data["reply"] = f"好的，我将围绕{course_name}的{topic}生成学习资源、练习题、学习计划和外部资料推荐。"

    tool_args = data.get("tool_args") if isinstance(data.get("tool_args"), dict) else {}
    for tool in tools:
        tool_args.setdefault(tool, {})
        if tool in {"generate_resource", "generate_quiz", "generate_plan", "search_external_learning_resources"}:
            tool_args[tool].setdefault("course_name", course_name)
            tool_args[tool].setdefault("topic", topic)
        if tool == "generate_plan":
            tool_args[tool].setdefault("days", data["days"])
        if tool == "search_external_learning_resources":
            tool_args[tool].setdefault("learner_level", "beginner")
            tool_args[tool].setdefault("max_results", 5)
    data["tool_args"] = tool_args

    return data


def analyze_user_learning_request(
        message: str,
        profile: dict | None = None,
        history: list[dict] | None = None
) -> dict:
    """
    总控智能体：理解用户自然语言需求，并规划后端工具调用。
    """
    history_text = json.dumps(history or [], ensure_ascii=False)
    profile_text = json.dumps(profile, ensure_ascii=False) if profile else "暂无学生画像"
    llm = get_llm()

    system_prompt = """
你是 A3 个性化学习系统的总控智能体，负责把用户自然语言请求转换成后端工具调用计划。

你只做规划，不直接生成长篇学习内容。你必须只输出严格 JSON，不要输出 Markdown，不要输出 JSON 以外的解释。

可用后端工具如下：

1. 学生画像
- generate_profile: 根据用户描述生成或更新学生画像。参数 tool_args.generate_profile = {"text": "画像描述文本"}。
- get_profile: 查询当前用户画像。参数为空对象。

2. 课程资料和 RAG
- create_material: 保存文本课程资料。参数 {"course_name": "...", "title": "...", "content": "..."}。
- list_materials: 查询课程资料列表。参数 {"course_name": null 或 "...", "page": 1, "size": 10}。
- build_material_index: 为资料构建检索索引。参数 {"material_id": 1}。必须有明确资料 id。
- rag_search_materials: 检索课程资料片段。参数 {"course_name": "...", "topic": "..."}。
注意：聊天接口不能上传文件。如果用户要上传 PDF/DOCX/TXT 文件，tools 必须为空，reply 引导用户到课程资料页面上传。

3. 学习资源
- generate_resource: 生成学习资源包。需要 course_name 和 topic，参数可为空或 {"course_name": "...", "topic": "..."}。
- list_resources: 查询学习资源列表。参数 {"page": 1, "size": 10}。
- get_resource: 查看学习资源详情。参数 {"resource_id": 1}。

4. 练习题和评测
- generate_quiz: 生成练习题。需要 course_name 和 topic，参数可为空或 {"course_name": "...", "topic": "..."}。
- list_quizzes: 查询题集列表。参数 {"page": 1, "size": 10}。
- get_quiz: 查看题集详情。参数 {"quiz_set_id": 1}。
- submit_evaluation: 提交答案并生成学习效果评估。参数 {"quiz_set_id": 1, "answers": [{"question_id": 1, "user_answer": "..."}]}。必须有题集 id 和明确答案。
- list_evaluations: 查询评估记录。参数 {"page": 1, "size": 10}。
- get_evaluation: 查看评估详情。参数 {"evaluation_id": 1}。

5. 学习计划和任务
- generate_plan: 生成学习计划预览。需要 course_name、topic、days。
- import_plan_tasks: 导入学习计划任务。参数 {"tasks_preview": [...]}；如果用户说“导入刚才的计划”，tool_args 可以为空，后端会尝试导入最近一次计划。
- create_task: 创建任务。参数 {"title": "...", "description": "", "status": "todo/doing/done", "priority": "low/medium/high"}。
- list_tasks: 查询任务。参数 {"status": null 或 "todo/doing/done", "page": 1, "size": 10}。
- get_task: 查看任务详情。参数 {"task_id": 1}。
- update_task: 更新任务。参数 {"task_id": 1, "title": null 或 "...", "description": null 或 "...", "status": null 或 "todo/doing/done", "priority": null 或 "low/medium/high"}。
- delete_task: 删除任务。参数 {"task_id": 1}。必须有明确任务 id。
- bulk_update_tasks_status: 批量更新任务状态。参数 {"from_status": "todo/doing/done", "to_status": "todo/doing/done"}。必须明确源状态和目标状态。
- bulk_delete_tasks_status: 按状态批量删除任务。参数 {"status": "todo/doing/done"}。必须明确状态。

6. 外部资源
- search_external_learning_resources: 联网搜索视频、文章、教程、文档等。需要 topic，course_name 可为空。参数 {"course_name": null 或 "...", "topic": "...", "learner_level": "beginner", "max_results": 5}。

7. 考试复习
- parse_exam_schedule: 解析考试安排文本。参数 {"text": "..."}。
- preview_review_plan: 根据考试安排生成复习计划预览。参数 {"exams": [{"course": "...", "exam_date": "YYYY-MM-DD", "exam_time": null 或 "HH:MM"}]}。如果和 parse_exam_schedule 同时调用，可以省略 exams，后端会使用解析结果。
- import_review_plan_tasks: 导入复习计划任务。参数 {"tasks_preview": [...]}；如果用户说“导入刚才的复习计划”，tool_args 可以为空，后端会尝试导入最近一次复习计划。

8. 日志
- list_operation_logs: 查询当前用户操作日志。参数 {"page": 1, "size": 10}。

字段提取规则：
- course_name 表示课程名，必须保留用户提供的完整课程名，例如“软件测试-A3内部课”不能简化。
- topic 表示具体知识点。
- days 表示学习天数；生成学习计划时用户没说则默认 3。
- available_time 表示每天可用学习时间；用户没说可默认“每天1小时”。
- resource_preference 表示资源偏好；用户没说可默认“图文讲解和练习题”。
- current_level 表示当前水平；用户没说不要编造，可为 null。
- 如果用户说“刚才那个”“这门课”“导入刚才的计划”，需要结合最近对话历史和工具结果补全。

信息是否足够：
- generate_resource、generate_quiz、generate_plan 必须有 course_name 和 topic；缺失时 status = need_more_info，tools = []，missing_fields 写缺失字段。
- rag_search_materials 必须有 course_name 和 topic。
- search_external_learning_resources 必须有 topic；course_name 可以为 null。
- get/detail/update/delete/build-index 类工具必须有明确 id；缺失 id 时追问。
- submit_evaluation 必须有 quiz_set_id 和 answers；缺失时追问。
- 任何删除或批量修改必须表达明确，不能猜测 id 或状态。

工具选择示例：
- “生成高数极限的讲解、练习题和三天计划” -> tools = ["generate_resource", "generate_quiz", "generate_plan"]
- “找几个单因子扰动原则的视频” -> tools = ["search_external_learning_resources"]
- “保存一份软件测试资料，标题边界值，内容是...” -> tools = ["create_material"]
- “列出我的 todo 任务” -> tools = ["list_tasks"]
- “把 12 号任务改成 done” -> tools = ["update_task"]
- “解析这些考试安排并生成复习计划” -> tools = ["parse_exam_schedule", "preview_review_plan"]
- “查看最近操作日志” -> tools = ["list_operation_logs"]

intent 可使用：
generate_study_package、generate_resource、generate_quiz、generate_plan、
generate_resource_only、generate_quiz_only、generate_plan_only、
search_external_learning_resources、update_profile、update_profile_request、
qa、chat、unknown，以及和具体后端工具同名的 intent。

输出格式必须严格如下：
{
  "reply": "给用户的简短回复或追问",
  "status": "need_more_info 或 ready_to_execute 或 chat_only",
  "intent": "上述工具名之一、generate_study_package、qa 或 unknown",
  "course_name": null,
  "topic": null,
  "days": 3,
  "available_time": null,
  "current_level": null,
  "resource_preference": null,
  "missing_fields": [],
  "tools": [],
  "tool_args": {},
  "need_confirm_import": false
}
"""

    human_prompt = f"""
当前学生画像:{profile_text}
最近对话历史:{history_text}
用户输入:{message}
"""
    result = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
    )
    content = _strip_json_fence(result.content)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("总控智能体返回的不是合法json")

    data = _apply_rule_based_fallback(data, message)
    data = _normalize_agent_plan(data)
    validated = AgentToolPlan.model_validate(data)
    return validated.model_dump()
