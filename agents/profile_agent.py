from pydantic import ValidationError

from llm_client import get_llm
from langchain_core.messages import HumanMessage,SystemMessage
import json

from models import StudentProfile


def generate_student_profile(text: str)-> dict:
    "根据用户自然语言描述生成学生画像"
    llm = get_llm()
    messages = [
        SystemMessage(
            content=(
                """你是一个学生画像生成助手。\n
                   请根据输入内容，来为学生生成json格式的学生画像，\n
                   生成格式要求如下 ：{
                          "grade": "大三",
                          "major": "软件工程",
                          "goals": ["期末复习", "实习准备"],
                          "weaknesses": ["算法", "SQL"],
                          "available_time": "每天2小时",
                          "learning_preference": "喜欢任务拆解和例题"
                        }
                    必须返回json格式，不要其他任何解释文字，不要markdown，\n
                    goals和weakness不存在时填入空列表，其他不存在的value信息填入null
                """
            )
        ),
        HumanMessage(content=text)
    ]
    result = llm.invoke(messages)
    content = result.content.strip()
    try:
        data = json.loads(content)
        profile = StudentProfile.model_validate( data)
        return profile.model_dump()
    except json.JSONDecodeError:
        raise ValueError(f"模型返回的json格式错误：{content}")
    except ValidationError as e:
        raise ValueError(f"学生画像字段校验失败：{e}")
if __name__ == "__main__":
    print(generate_student_profile("李明，男，2004 年 3 月出生，2022 级计算机科学与技术专业全日制本科生，学号 20220501036。该生在校遵纪守法、尊敬师长、团结同学，日常遵守校纪班规，学习态度端正，能够按时完成课业任务，已修习多门专业基础课程，学业成绩整体达标，课余参与社团及班级集体活动，综合表现良好，个别学科仍需加强课后复习巩固。"))