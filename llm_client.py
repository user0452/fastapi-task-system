import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage,HumanMessage
import json

load_dotenv()

def get_llm():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL")
    model = os.getenv("DEEPSEEK_MODEL")

    if not api_key:
        raise RuntimeError("LLM_API_KEY 未配置")

    if not base_url:
        raise RuntimeError("LLM_BASE_URL 未配置")

    if not model:
        raise RuntimeError("LLM_MODEL 未配置")

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model
    )
def ask_llm(user_text:str):
    llm = get_llm()
    messages = [
        SystemMessage(content="你是一个助手，请根据用户输入的文本，生成一个符合要求的JSON格式的指令"),
        HumanMessage(content=user_text)
    ]
    result = llm.invoke(messages)
    return result.content

def parse_exam_shedule(text: str)-> dict:
    llm = get_llm()
    messages = [
        SystemMessage(
            content=(
                "你是一个考试安排解析助手。\n"
                "请从用户输入中提取考试信息。\n"
                "你必须只返回 JSON，不要返回解释文字，不要使用 Markdown。\n"
                "返回格式必须严格如下：\n"
                '{\n'
                '  "exams": [\n'
                '    {\n'
                '      "course": "课程名",\n'
                '      "exam_date": "YYYY-MM-DD",\n'
                '      "exam_time": "HH:MM 或 null"\n'
                '    }\n'
                '  ]\n'
                '}\n'
                "如果没有明确时间，exam_time 填 null。\n"
                "如果没有明确日期，尽量根据文本推断；无法推断就不要生成该考试。"
            )
        ),
        HumanMessage(content=text),
    ]
    result = llm.invoke(messages)
    content = result.content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise ValueError(f"模型返回的不是合法json：{ content}")

def preview_review_plan(exams: list[dict])-> dict:
    llm = get_llm()
    messages = [
        SystemMessage (
            content=(
                "你是一个复习任务规划助手。\n"
                "请根据考试安排生成复习任务预览。\n"
                "你必须只返回 JSON，不要返回解释文字，不要使用 Markdown。\n"
                "返回格式必须严格如下：\n"
                "{\n"
                '  "tasks_preview": [\n'
                "    {\n"
                '      "title": "任务标题",\n'
                '      "description": "任务描述",\n'
                '      "status": "todo",\n'
                '      "priority": "low/medium/high"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "每门考试生成 2 到 3 个复习任务。\n"
                "任务标题要具体，不能太空泛。\n"
                "description 要说明具体复习内容。\n"
                "status 固定为 todo。\n"
                "priority 只能是 low、medium、high。\n"
                "临近考试的科目优先级更高。"
            )
        ),
        HumanMessage(
            content=(f"考试安排如下：\n{exams}")
        )
    ]
    result = llm.invoke(messages)
    content = result.content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise ValueError(f"模型返回的不是合法json：{ content}")