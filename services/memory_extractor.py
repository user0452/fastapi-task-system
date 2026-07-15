"""
记忆提取器
从对话中提取值得长期记住的信息
"""

import json
from langchain_core.messages import SystemMessage, HumanMessage
from llm_client import invoke_agent_messages


class MemoryExtractor:
    """从对话中提取记忆"""

    def extract_from_conversation(
        self,
        user_message: str,
        ai_response: str,
        context: dict = None
    ) -> list[dict]:
        """
        从对话中提取有价值的记忆

        Args:
            user_message: 用户消息
            ai_response: AI 回复
            context: 额外上下文（课程名、知识点等）

        Returns:
            提取的记忆列表
        """
        context_text = ""
        if context:
            context_parts = []
            if context.get("course_name"):
                context_parts.append(f"课程：{context['course_name']}")
            if context.get("topic"):
                context_parts.append(f"知识点：{context['topic']}")
            if context_parts:
                context_text = "\n上下文：" + "，".join(context_parts)

        prompt = f"""分析以下对话，提取值得长期记住的信息。

用户: {user_message}
AI: {ai_response}
{context_text}

请以 JSON 数组格式返回提取的记忆，每条记忆包含:
- type: 记忆类型
  - "preference": 用户偏好（学习方式、资料类型等）
  - "weakness": 薄弱点（不理解的概念、常犯的错误）
  - "strength": 优势（掌握好的技能）
  - "goal": 学习目标
  - "fact": 关于用户的事实（专业、年级等）
  - "habit": 学习习惯
- content: 记忆内容（简洁明确，10-50字）
- importance: 0-1 重要性评分
  - 0.9-1.0: 关键信息（考试、核心目标）
  - 0.7-0.8: 重要信息（薄弱点、偏好）
  - 0.5-0.6: 一般信息（习惯、事实）
  - 0.3-0.4: 次要信息

提取原则：
1. 只提取明确、具体的信息，不要提取泛泛而谈的内容
2. 优先提取对个性化教学有价值的信息
3. 同一类信息只提取最核心的1-2条
4. 如果没有值得记住的信息，返回空数组 []

示例输出:
[
    {{"type": "preference", "content": "喜欢图文并茂的学习资料", "importance": 0.7}},
    {{"type": "weakness", "content": "对等价类划分的边界情况理解较弱", "importance": 0.8}},
    {{"type": "goal", "content": "希望三天内掌握软件测试基础", "importance": 0.9}}
]

请直接返回 JSON 数组，不要添加其他文字。"""

        try:
            result = invoke_agent_messages([
                SystemMessage(content="你是一个专业的记忆提取助手，专注于从对话中提取有价值的学习相关信息。"),
                HumanMessage(content=prompt)
            ]).message

            content = result.content.strip()

            # 处理可能的 markdown 格式
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines).strip()

            memories = json.loads(content)

            if not isinstance(memories, list):
                return []

            # 验证和清理
            valid_types = {"preference", "weakness", "strength", "goal", "fact", "habit"}
            cleaned = []

            for memory in memories:
                if not isinstance(memory, dict):
                    continue

                mem_type = memory.get("type", "")
                mem_content = memory.get("content", "")
                mem_importance = memory.get("importance", 0.5)

                if mem_type not in valid_types:
                    continue
                if not mem_content or len(mem_content) < 5:
                    continue
                if not isinstance(mem_importance, (int, float)):
                    mem_importance = 0.5

                # 限制长度
                if len(mem_content) > 100:
                    mem_content = mem_content[:100]

                cleaned.append({
                    "type": mem_type,
                    "content": mem_content,
                    "importance": max(0.1, min(1.0, float(mem_importance)))
                })

            return cleaned[:5]  # 最多返回5条

        except Exception as e:
            print(f"记忆提取失败: {e}")
            return []

    def extract_from_profile(self, profile_text: str) -> list[dict]:
        """从学生画像描述中提取记忆"""

        prompt = f"""从以下学生画像描述中提取关键信息。

描述: {profile_text}

请以 JSON 数组格式返回提取的记忆，每条记忆包含:
- type: "fact" | "goal" | "weakness" | "preference"
- content: 简洁明确的记忆内容
- importance: 0-1 重要性评分

提取关键信息：专业、年级、学习目标、薄弱环节、学习偏好等。

请直接返回 JSON 数组。"""

        try:
            result = invoke_agent_messages([
                SystemMessage(content="你是一个信息提取助手。"),
                HumanMessage(content=prompt)
            ]).message

            content = result.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                content = "\n".join(lines).strip()

            memories = json.loads(content)
            return memories if isinstance(memories, list) else []

        except Exception:
            return []

    def generate_summary(self, content: str, max_length: int = 50) -> str:
        """生成记忆摘要"""

        prompt = f"""请用一句话概括以下内容，不超过{max_length}个字。

内容: {content}

摘要:"""

        try:
            result = invoke_agent_messages([
                SystemMessage(content="你是一个摘要生成助手。"),
                HumanMessage(content=prompt)
            ]).message

            summary = result.content.strip()
            if len(summary) > max_length:
                summary = summary[:max_length] + "..."

            return summary

        except Exception:
            return content[:max_length] + "..." if len(content) > max_length else content


# 全局记忆提取器实例
memory_extractor = MemoryExtractor()
