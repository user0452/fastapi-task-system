"""
AI 长期记忆服务
基于 MySQL + Embedding 实现语义检索
"""

import json
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Any
from db import get_cursor
from services.rag_service import get_embedding_model


class MemoryService:
    """AI 长期记忆服务"""

    def __init__(self):
        self._embedding_model = None

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            self._embedding_model = get_embedding_model()
        return self._embedding_model

    def _get_embedding(self, text: str) -> list[float]:
        """获取文本的 embedding 向量"""
        embedding = self.embedding_model.encode([text], normalize_embeddings=True)
        return embedding[0].tolist()

    def _calculate_similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        """计算两个向量的余弦相似度"""
        a = np.array(embedding1)
        b = np.array(embedding2)
        return float(np.dot(a, b))

    def save_memory(
        self,
        user_id: int,
        content: str,
        memory_type: str = "episodic",
        category: str = None,
        summary: str = None,
        metadata: dict = None,
        source: str = "conversation",
        importance: float = 0.5,
        confidence: float = 0.8,
        expires_days: int = None
    ) -> int:
        """
        保存一条记忆

        Args:
            user_id: 用户 ID
            content: 记忆内容
            memory_type: 记忆类型 (episodic/semantic/procedural)
            category: 分类 (preference/weakness/goal/fact/habit/strength)
            summary: 摘要
            metadata: 元数据
            source: 来源 (conversation/behavior/explicit)
            importance: 重要性 0-1
            confidence: 置信度 0-1
            expires_days: 过期天数，None 表示永不过期

        Returns:
            记忆 ID
        """
        # 生成 embedding
        embedding_json = json.dumps(self._get_embedding(content))

        # 计算过期时间
        expires_at = None
        if expires_days:
            expires_at = datetime.now() + timedelta(days=expires_days)

        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ai_memories
                    (user_id, memory_type, category, content, summary,
                     metadata, source, embedding_json, importance, confidence,
                     expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, memory_type, category, content, summary,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    source, embedding_json, importance, confidence,
                    expires_at
                )
            )
            memory_id = cursor.lastrowid

            # 记录访问日志
            cursor.execute(
                """
                INSERT INTO memory_access_logs
                    (memory_id, user_id, access_type)
                VALUES (%s, %s, 'create')
                """,
                (memory_id, user_id)
            )

            return memory_id

    def recall(
        self,
        user_id: int,
        query: str,
        memory_type: str = None,
        category: str = None,
        top_k: int = 5,
        min_importance: float = 0.0,
        min_confidence: float = 0.0
    ) -> list[dict]:
        """
        检索相关记忆

        Args:
            user_id: 用户 ID
            query: 查询文本
            memory_type: 过滤记忆类型
            category: 过滤分类
            top_k: 返回数量
            min_importance: 最小重要性
            min_confidence: 最小置信度

        Returns:
            相关记忆列表
        """
        query_embedding = self._get_embedding(query)

        with get_cursor() as cursor:
            # 构建查询
            sql = """
                SELECT id, memory_type, category, content, summary,
                       metadata, source, importance, confidence,
                       access_count, embedding_json, created_at
                FROM ai_memories
                WHERE user_id = %s
                  AND is_active = TRUE
                  AND importance >= %s
                  AND confidence >= %s
                  AND (expires_at IS NULL OR expires_at > NOW())
            """
            params = [user_id, min_importance, min_confidence]

            if memory_type:
                sql += " AND memory_type = %s"
                params.append(memory_type)

            if category:
                sql += " AND category = %s"
                params.append(category)

            sql += " ORDER BY importance DESC, created_at DESC LIMIT 200"

            cursor.execute(sql, params)
            memories = cursor.fetchall()

            if not memories:
                return []

            # 计算相似度并排序
            results = []
            for memory in memories:
                if memory['embedding_json']:
                    memory_embedding = json.loads(memory['embedding_json'])
                    similarity = self._calculate_similarity(query_embedding, memory_embedding)

                    # 综合评分：相似度 * 0.6 + 重要性 * 0.3 + 置信度 * 0.1
                    score = similarity * 0.6 + memory['importance'] * 0.3 + memory['confidence'] * 0.1

                    results.append({
                        'id': memory['id'],
                        'memory_type': memory['memory_type'],
                        'category': memory['category'],
                        'content': memory['content'],
                        'summary': memory['summary'],
                        'metadata': json.loads(memory['metadata']) if memory['metadata'] else {},
                        'source': memory['source'],
                        'importance': memory['importance'],
                        'confidence': memory['confidence'],
                        'similarity': similarity,
                        'score': score,
                        'created_at': memory['created_at'].isoformat() if memory['created_at'] else None
                    })

            # 按综合评分排序
            results.sort(key=lambda x: x['score'], reverse=True)

            # 更新访问计数
            top_ids = [r['id'] for r in results[:top_k]]
            if top_ids:
                placeholders = ','.join(['%s'] * len(top_ids))
                cursor.execute(
                    f"""
                    UPDATE ai_memories
                    SET access_count = access_count + 1,
                        last_accessed_at = NOW()
                    WHERE id IN ({placeholders})
                    """,
                    top_ids
                )

                # 记录访问日志
                for memory in results[:top_k]:
                    cursor.execute(
                        """
                        INSERT INTO memory_access_logs
                            (memory_id, user_id, access_type, query_text, relevance_score)
                        VALUES (%s, %s, 'recall', %s, %s)
                        """,
                        (memory['id'], user_id, query, memory['score'])
                    )

            return results[:top_k]

    def get_user_memories(
        self,
        user_id: int,
        memory_type: str = None,
        category: str = None,
        page: int = 1,
        size: int = 20
    ) -> dict:
        """获取用户的记忆列表"""
        with get_cursor() as cursor:
            sql = """
                SELECT COUNT(*) as total
                FROM ai_memories
                WHERE user_id = %s AND is_active = TRUE
            """
            params = [user_id]

            if memory_type:
                sql += " AND memory_type = %s"
                params.append(memory_type)

            if category:
                sql += " AND category = %s"
                params.append(category)

            cursor.execute(sql, params)
            total = cursor.fetchone()['total']

            # 获取分页数据
            offset = (page - 1) * size
            sql = """
                SELECT id, memory_type, category, content, summary,
                       importance, confidence, access_count,
                       last_accessed_at, created_at
                FROM ai_memories
                WHERE user_id = %s AND is_active = TRUE
            """
            params = [user_id]

            if memory_type:
                sql += " AND memory_type = %s"
                params.append(memory_type)

            if category:
                sql += " AND category = %s"
                params.append(category)

            sql += " ORDER BY importance DESC, created_at DESC LIMIT %s OFFSET %s"
            params.extend([size, offset])

            cursor.execute(sql, params)
            memories = cursor.fetchall()

            return {
                'total': total,
                'page': page,
                'size': size,
                'items': [
                    {
                        'id': m['id'],
                        'memory_type': m['memory_type'],
                        'category': m['category'],
                        'content': m['content'],
                        'summary': m['summary'],
                        'importance': m['importance'],
                        'confidence': m['confidence'],
                        'access_count': m['access_count'],
                        'last_accessed_at': m['last_accessed_at'].isoformat() if m['last_accessed_at'] else None,
                        'created_at': m['created_at'].isoformat() if m['created_at'] else None
                    }
                    for m in memories
                ]
            }

    def update_memory(
        self,
        memory_id: int,
        user_id: int,
        content: str = None,
        summary: str = None,
        importance: float = None,
        confidence: float = None,
        category: str = None
    ) -> bool:
        """更新记忆"""
        with get_cursor() as cursor:
            # 验证所有权
            cursor.execute(
                "SELECT id FROM ai_memories WHERE id = %s AND user_id = %s",
                (memory_id, user_id)
            )
            if not cursor.fetchone():
                return False

            updates = []
            params = []

            if content is not None:
                updates.append("content = %s")
                params.append(content)
                # 重新生成 embedding
                updates.append("embedding_json = %s")
                params.append(json.dumps(self._get_embedding(content)))

            if summary is not None:
                updates.append("summary = %s")
                params.append(summary)

            if importance is not None:
                updates.append("importance = %s")
                params.append(importance)

            if confidence is not None:
                updates.append("confidence = %s")
                params.append(confidence)

            if category is not None:
                updates.append("category = %s")
                params.append(category)

            if not updates:
                return False

            params.append(memory_id)
            sql = f"UPDATE ai_memories SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(sql, params)

            return True

    def delete_memory(self, memory_id: int, user_id: int) -> bool:
        """删除记忆（软删除）"""
        with get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE ai_memories
                SET is_active = FALSE
                WHERE id = %s AND user_id = %s
                """,
                (memory_id, user_id)
            )
            return cursor.rowcount > 0

    def forget_old_memories(self, user_id: int, days: int = 90) -> int:
        """遗忘旧记忆"""
        with get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE ai_memories
                SET is_active = FALSE
                WHERE user_id = %s
                  AND is_active = TRUE
                  AND last_accessed_at < DATE_SUB(NOW(), INTERVAL %s DAY)
                  AND access_count < 3
                  AND importance < 0.7
                """,
                (user_id, days)
            )
            return cursor.rowcount

    def get_memory_stats(self, user_id: int) -> dict:
        """获取记忆统计"""
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    memory_type,
                    category,
                    COUNT(*) as count,
                    AVG(importance) as avg_importance,
                    AVG(access_count) as avg_access
                FROM ai_memories
                WHERE user_id = %s AND is_active = TRUE
                GROUP BY memory_type, category
                """,
                (user_id,)
            )
            stats = cursor.fetchall()

            cursor.execute(
                "SELECT COUNT(*) as total FROM ai_memories WHERE user_id = %s AND is_active = TRUE",
                (user_id,)
            )
            total = cursor.fetchone()['total']

            return {
                'total': total,
                'by_type': [
                    {
                        'memory_type': s['memory_type'],
                        'category': s['category'],
                        'count': s['count'],
                        'avg_importance': round(float(s['avg_importance']), 2),
                        'avg_access': round(float(s['avg_access']), 2)
                    }
                    for s in stats
                ]
            }


# 全局记忆服务实例
memory_service = MemoryService()
