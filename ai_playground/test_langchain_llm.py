from llm_client import ask_llm,parse_exam_shedule

text = """
高数 2026-06-10 09:00
英语 2026-06-13 15:00
"""

result = parse_exam_shedule(text)
print(result)