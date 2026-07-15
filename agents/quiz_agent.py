import json
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError
from llm_client import invoke_agent_messages
from models import QuizSet
from services.rag_service import search_similar_chunks


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


def _load_quiz_json(content: str) -> dict:
    text = _strip_json_fence(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError as original_error:
        repair_result = invoke_agent_messages([
            SystemMessage(
                content=(
                    "你是 JSON 修复器。请把用户给出的内容修复成合法 JSON。\n"
                    "只返回修复后的 JSON，不要返回解释文字，不要使用 Markdown。\n"
                    "不要改变字段结构和题目含义。\n"
                    "如果字符串内部有未转义的英文双引号，请转义或改成中文引号/单引号。"
                )
            ),
            HumanMessage(content=f"需要修复的内容如下：\n{text}")
        ]).message
        repaired = _strip_json_fence(repair_result.content)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            raise ValueError(f"模型返回的json格式错误：{content}") from original_error

def generate_quiz_set(course_name: str,topic: str,profile:dict|None = None,rag_context:list[dict]|None = None) -> dict:
    rag_context_text = "暂无课程资料检索结果"
    if rag_context:
        rag_context_text = "\n\n".join(
            [
                f"资料片段{index + 1}：{item.get('chunk_text', '')}"
                for index, item in enumerate(rag_context)
            ]
        )

    messages = [
        SystemMessage(
            content=(
                "你是一个个性化练习题生成助手。\n"
                "请根据课程名、知识点和学生画像，生成一组适合该学生的练习题。\n"
                "必须严格围绕用户提供的课程名和知识点生成题目。\n"
                "学生画像只用于调整题目难度、表达方式和例子风格，不能改变课程主题。\n"
                "你必须只返回 JSON，不要返回解释文字，不要使用 Markdown。\n"
                "返回格式必须严格如下：\n"
                "{\n"
                '  "title": "练习题标题",\n'
                '  "course_name": "课程名",\n'
                '  "topic": "知识点",\n'
                '  "questions": [\n'
                "    {\n"
                '      "question_type": "choice/short_answer/coding",\n'
                '      "question": "题目内容",\n'
                '      "answer": "参考答案",\n'
                '      "difficulty": "easy/medium/hard"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "question_type 只能是 choice、short_answer、coding。\n"
                "difficulty 只能是 easy、medium、hard。\n"
                "第一版请优先生成 short_answer 类型题目。\n"
                "所有字符串字段内部不要使用未转义的英文双引号；举例字符串时请写成 'abc' 或 中文引号“abc”。\n"
                "请生成 3 到 5 道题。"
            )
        ),
        HumanMessage (
            content=(
                f"请为课程{course_name}的{topic},考生画像为{profile},生成考题，请使用以下格式：\n"
                f"""
                课程资料检索结果：
                {rag_context_text}
                
                出题要求：
                - 如果提供了课程资料检索结果，题目必须优先基于这些资料设计。
                - 不要编造课程资料中没有出现的专有概念。
                - 题目要围绕 course_name 和 topic。
                - 如果课程资料里有自定义术语，题目必须体现这些术语。
                """
            )
        )
    ]
    result = invoke_agent_messages(messages).message
    content = result.content.strip()
    try:
        data = _load_quiz_json(content)
        quiz_set = QuizSet.model_validate(data)
        return quiz_set.model_dump()
    except ValidationError as e:
        raise ValueError(f"练习题字段校验失败:{e}")

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
        generate_quiz_set(
            course_name="软件测试",
            topic="等价类划分",
            profile=test_profile
        )
    )
