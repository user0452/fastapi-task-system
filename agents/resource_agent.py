from llm_client import get_llm
import json
from langchain_core.messages import HumanMessage,SystemMessage
from pydantic import ValidationError
from models import LearningResource


def generate_learning_resource(
        course_name:str,
        topic:str,
        profile:dict |None = None,
        rag_context: list[dict] | None = None
)->dict:
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
                "你是一个个性化学习资源生成助手。\n"
                "请根据课程名、知识点和学生画像，生成一份适合该学生学习的知识点讲解资源。\n"
                "必须严格围绕用户提供的课程名和知识点生成内容。\n"
                "如果课程名或知识点过于宽泛，可以生成该课程的复习总览，但不能擅自切换到其他课程方向。\n"
                "学生画像只用于调整讲解难度、例子风格和表达方式，不能改变课程主题。\n"
                "你必须只返回 JSON，不要返回解释文字，不要使用 Markdown。\n"
                "返回格式必须严格如下：\n"
                "{\n"
                '  "title": "资源标题",\n'
                '  "resource_type": "explanation",\n'
                '  "content": "知识点讲解正文",\n'
                '  "key_points": ["关键点1", "关键点2"],\n'
                '  "examples": ["例子1", "例子2"]\n'
                "}\n"
                "resource_type 固定为 explanation。\n"
                "content 要适合学生当前水平，不要太空泛。\n"
                "key_points 和 examples 不存在时返回空数组 []。"
            )
        ),
        HumanMessage(
            content=f"课程名：{course_name}\n"
                    f"知识点：{topic}\n"
                    f"学生画像：{json.dumps(profile,ensure_ascii=False)}"
                    f"""课程资料检索结果：
                    {rag_context_text}
                    
                    要求：
                    - 如果提供了课程资料检索结果，必须优先基于这些资料生成。
                    - 不要编造课程资料中没有明确支持的细节。
                    - 如果需要补充通用知识，可以补充，但要保持和课程资料一致。"""
        )
    ]
    result = llm.invoke(messages)
    content = result.content.strip()

    try:
        data = json.loads(content)
        resource = LearningResource.model_validate( data)
        return resource.model_dump()
    except json.JSONDecodeError:
        raise ValueError(f"模型返回的json格式错误：{content}")
    except ValidationError as e:
        raise ValueError(f"模型返回的json数据验证失败：{e.json()}")

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
        generate_learning_resource(
            course_name="软件测试",
            topic="等价类划分",
            profile=test_profile
        )
    )