import json
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError
from llm_client import get_llm
from models import QuizSet
from services.rag_service import search_similar_chunks

def generate_quiz_set(course_name: str,topic: str,profile:dict|None = None,rag_context:list[dict]|None = None) -> dict:
    llm = get_llm()
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
    result = llm.invoke(messages)
    content = result.content.strip()
    try:
        data = json.loads(content)
        quiz_set = QuizSet.model_validate(data)
        return quiz_set.model_dump()
    except json.JSONDecodeError:
        raise ValueError(f"模型返回的json格式错误：{content}")
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
