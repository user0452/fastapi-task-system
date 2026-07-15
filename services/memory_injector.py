"""
记忆注入器
将长期记忆注入到 Agent 的 prompt 中
"""

from services.memory_service import memory_service


class MemoryInjector:
    """将记忆注入到 prompt 中"""

    def build_memory_context(
        self,
        user_id: int,
        current_query: str,
        memory_type: str = None,
        max_items: int = 5,
        max_chars: int = 500
    ) -> str:
        """
        构建记忆上下文

        Args:
            user_id: 用户 ID
            current_query: 当前查询
            memory_type: 过滤记忆类型
            max_items: 最大记忆条数
            max_chars: 最大字符数

        Returns:
            格式化的记忆上下文文本
        """
        # 检索相关记忆
        memories = memory_service.recall(
            user_id=user_id,
            query=current_query,
            memory_type=memory_type,
            top_k=max_items
        )

        if not memories:
            return ""

        # 按类型组织记忆
        memory_by_type = {
            "preference": [],
            "weakness": [],
            "strength": [],
            "goal": [],
            "fact": [],
            "habit": []
        }

        for memory in memories:
            category = memory.get("category", "fact")
            if category in memory_by_type:
                memory_by_type[category].append(memory["content"])

        # 构建上下文文本
        context_parts = []

        if memory_by_type["goal"]:
            context_parts.append("学习目标：" + "；".join(memory_by_type["goal"][:2]))

        if memory_by_type["weakness"]:
            context_parts.append("薄弱环节：" + "；".join(memory_by_type["weakness"][:2]))

        if memory_by_type["preference"]:
            context_parts.append("学习偏好：" + "；".join(memory_by_type["preference"][:2]))

        if memory_by_type["strength"]:
            context_parts.append("掌握较好：" + "；".join(memory_by_type["strength"][:2]))

        if memory_by_type["fact"]:
            context_parts.append("已知信息：" + "；".join(memory_by_type["fact"][:2]))

        if memory_by_type["habit"]:
            context_parts.append("学习习惯：" + "；".join(memory_by_type["habit"][:1]))

        context = "\n".join(context_parts)

        # 截断到最大字符数
        if len(context) > max_chars:
            context = context[:max_chars] + "..."

        return context

    def enhance_message_with_memory(
        self,
        user_id: int,
        message: str,
        include_memory: bool = True
    ) -> str:
        """
        用记忆增强用户消息

        Args:
            user_id: 用户 ID
            message: 原始消息
            include_memory: 是否包含记忆

        Returns:
            增强后的消息
        """
        if not include_memory:
            return message

        memory_context = self.build_memory_context(
            user_id=user_id,
            current_query=message
        )

        if not memory_context:
            return message

        return f"""【用户历史记忆】
{memory_context}

【当前问题】
{message}

请结合用户的历史记忆，提供更个性化的回答。如果记忆中有用户的薄弱点，可以重点讲解；如果有学习偏好，可以调整回答风格。"""

    def build_system_prompt_with_memory(
        self,
        user_id: int,
        base_prompt: str,
        current_query: str
    ) -> str:
        """
        构建包含记忆的系统提示词

        Args:
            user_id: 用户 ID
            base_prompt: 基础提示词
            current_query: 当前查询

        Returns:
            包含记忆的系统提示词
        """
        memory_context = self.build_memory_context(
            user_id=user_id,
            current_query=current_query,
            max_items=10,
            max_chars=800
        )

        if not memory_context:
            return base_prompt

        return f"""{base_prompt}

【用户画像记忆】
以下是关于该用户的历史记忆，请在回答时参考：
{memory_context}

注意事项：
1. 如果用户有明确的薄弱点，回答时可以多举例、多解释
2. 如果用户有学习偏好，尽量按照偏好调整回答风格
3. 如果用户有明确的学习目标，回答要围绕目标展开
4. 不要直接告诉用户你知道这些记忆，自然地融入回答中"""


# 全局记忆注入器实例
memory_injector = MemoryInjector()
