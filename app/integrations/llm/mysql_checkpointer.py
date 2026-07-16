"""MySQL-backed LangGraph checkpointer used by interruptible agents."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)

from app.core.database import get_cursor


class MySQLCheckpointSaver(BaseCheckpointSaver[str]):
    """Stateless saver; every operation uses a short pooled DB transaction."""

    @staticmethod
    def _config(thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> RunnableConfig:
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def _load_tuple(self, row: dict) -> CheckpointTuple:
        thread_id = row["thread_id"]
        checkpoint_ns = row["checkpoint_ns"]
        checkpoint_id = row["checkpoint_id"]
        checkpoint = self.serde.loads_typed(
            (row["checkpoint_type"], bytes(row["checkpoint_blob"]))
        )
        versions = checkpoint.get("channel_versions", {})
        channel_values: dict[str, Any] = {}
        pending_writes: list[tuple[str, str, Any]] = []
        with get_cursor() as cursor:
            for channel, version in versions.items():
                cursor.execute(
                    """
                    SELECT value_type, value_blob
                    FROM agent_graph_checkpoint_blobs
                    WHERE thread_id = %s AND checkpoint_ns = %s
                      AND channel_name = %s AND channel_version = %s
                    """,
                    (thread_id, checkpoint_ns, channel, str(version)),
                )
                blob = cursor.fetchone()
                if blob and blob["value_type"] != "empty":
                    channel_values[channel] = self.serde.loads_typed(
                        (blob["value_type"], bytes(blob["value_blob"]))
                    )
            cursor.execute(
                """
                SELECT task_id, channel_name, value_type, value_blob
                FROM agent_graph_checkpoint_writes
                WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s
                ORDER BY task_id, write_index
                """,
                (thread_id, checkpoint_ns, checkpoint_id),
            )
            for write in cursor.fetchall():
                pending_writes.append(
                    (
                        write["task_id"],
                        write["channel_name"],
                        self.serde.loads_typed(
                            (write["value_type"], bytes(write["value_blob"]))
                        ),
                    )
                )
        checkpoint["channel_values"] = channel_values
        parent_id = row.get("parent_checkpoint_id")
        return CheckpointTuple(
            config=self._config(thread_id, checkpoint_ns, checkpoint_id),
            checkpoint=checkpoint,
            metadata=self.serde.loads_typed(
                (row["metadata_type"], bytes(row["metadata_blob"]))
            ),
            pending_writes=pending_writes,
            parent_config=(
                self._config(thread_id, checkpoint_ns, parent_id) if parent_id else None
            ),
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = get_checkpoint_id(config)
        with get_cursor() as cursor:
            if checkpoint_id:
                cursor.execute(
                    """
                    SELECT * FROM agent_graph_checkpoints
                    WHERE thread_id = %s AND checkpoint_ns = %s AND checkpoint_id = %s
                    """,
                    (thread_id, checkpoint_ns, checkpoint_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM agent_graph_checkpoints
                    WHERE thread_id = %s AND checkpoint_ns = %s
                    ORDER BY checkpoint_id DESC LIMIT 1
                    """,
                    (thread_id, checkpoint_ns),
                )
            row = cursor.fetchone()
        return self._load_tuple(row) if row else None

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        clauses: list[str] = []
        params: list[Any] = []
        if config:
            configurable = config["configurable"]
            clauses.append("thread_id = %s")
            params.append(str(configurable["thread_id"]))
            if "checkpoint_ns" in configurable:
                clauses.append("checkpoint_ns = %s")
                params.append(str(configurable.get("checkpoint_ns", "")))
            if checkpoint_id := get_checkpoint_id(config):
                clauses.append("checkpoint_id = %s")
                params.append(checkpoint_id)
        if before and (before_id := get_checkpoint_id(before)):
            clauses.append("checkpoint_id < %s")
            params.append(before_id)
        sql = "SELECT * FROM agent_graph_checkpoints"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY checkpoint_id DESC"
        with get_cursor() as cursor:
            cursor.execute(sql, params)
            rows = list(cursor.fetchall())
        yielded = 0
        for row in rows:
            item = self._load_tuple(row)
            if filter and not all(item.metadata.get(key) == value for key, value in filter.items()):
                continue
            yield item
            yielded += 1
            if limit is not None and yielded >= limit:
                break

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        copy: dict[str, Any] = dict(checkpoint)
        values = copy.pop("channel_values", {})
        checkpoint_type, checkpoint_blob = self.serde.dumps_typed(copy)
        metadata_type, metadata_blob = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )
        with get_cursor() as cursor:
            for channel, version in new_versions.items():
                if channel in values:
                    value_type, value_blob = self.serde.dumps_typed(values[channel])
                else:
                    value_type, value_blob = "empty", b""
                cursor.execute(
                    """
                    INSERT INTO agent_graph_checkpoint_blobs
                        (thread_id, checkpoint_ns, channel_name, channel_version,
                         value_type, value_blob)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        value_type = VALUES(value_type), value_blob = VALUES(value_blob)
                    """,
                    (
                        thread_id, checkpoint_ns, channel, str(version),
                        value_type, value_blob,
                    ),
                )
            cursor.execute(
                """
                INSERT INTO agent_graph_checkpoints
                    (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                     checkpoint_type, checkpoint_blob, metadata_type, metadata_blob)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    parent_checkpoint_id = VALUES(parent_checkpoint_id),
                    checkpoint_type = VALUES(checkpoint_type),
                    checkpoint_blob = VALUES(checkpoint_blob),
                    metadata_type = VALUES(metadata_type),
                    metadata_blob = VALUES(metadata_blob)
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint["id"],
                    configurable.get("checkpoint_id"),
                    checkpoint_type,
                    checkpoint_blob,
                    metadata_type,
                    metadata_blob,
                ),
            )
        return self._config(thread_id, checkpoint_ns, checkpoint["id"])

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        configurable = config["configurable"]
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(configurable["checkpoint_id"])
        with get_cursor() as cursor:
            for position, (channel, value) in enumerate(writes):
                index = WRITES_IDX_MAP.get(channel, position)
                value_type, value_blob = self.serde.dumps_typed(value)
                if index < 0:
                    cursor.execute(
                        """
                        INSERT IGNORE INTO agent_graph_checkpoint_writes
                            (thread_id, checkpoint_ns, checkpoint_id, task_id,
                             write_index, channel_name, value_type, value_blob, task_path)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            thread_id, checkpoint_ns, checkpoint_id, task_id, index,
                            channel, value_type, value_blob, task_path,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO agent_graph_checkpoint_writes
                            (thread_id, checkpoint_ns, checkpoint_id, task_id,
                             write_index, channel_name, value_type, value_blob, task_path)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            channel_name = VALUES(channel_name),
                            value_type = VALUES(value_type),
                            value_blob = VALUES(value_blob),
                            task_path = VALUES(task_path)
                        """,
                        (
                            thread_id, checkpoint_ns, checkpoint_id, task_id, index,
                            channel, value_type, value_blob, task_path,
                        ),
                    )

    def delete_thread(self, thread_id: str) -> None:
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM agent_graph_checkpoint_writes WHERE thread_id = %s",
                (thread_id,),
            )
            cursor.execute(
                "DELETE FROM agent_graph_checkpoints WHERE thread_id = %s",
                (thread_id,),
            )
            cursor.execute(
                "DELETE FROM agent_graph_checkpoint_blobs WHERE thread_id = %s",
                (thread_id,),
            )

    def gc_stale_threads(self, cutoff: datetime) -> int:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT thread_id
                FROM agent_graph_checkpoints
                GROUP BY thread_id
                HAVING MAX(created_at) < %s
                """,
                (cutoff,),
            )
            candidates = {str(row["thread_id"]) for row in cursor.fetchall()}
            cursor.execute(
                """
                SELECT checkpoint_json
                FROM agent_action_requests
                WHERE status IN ('pending', 'resuming')
                  AND checkpoint_json IS NOT NULL
                """
            )
            active_threads: set[str] = set()
            for row in cursor.fetchall():
                value = row.get("checkpoint_json")
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                        if isinstance(value, str):
                            value = json.loads(value)
                    except (TypeError, json.JSONDecodeError):
                        value = None
                if isinstance(value, dict) and value.get("thread_id"):
                    active_threads.add(str(value["thread_id"]))
            thread_ids = sorted(candidates - active_threads)
        for thread_id in thread_ids:
            self.delete_thread(thread_id)
        return len(thread_ids)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(self, config, checkpoint, metadata, new_versions):
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path="") -> None:
        self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        self.delete_thread(thread_id)


_SAVER = MySQLCheckpointSaver()


def get_mysql_checkpointer() -> MySQLCheckpointSaver:
    return _SAVER


__all__ = ["MySQLCheckpointSaver", "get_mysql_checkpointer"]
