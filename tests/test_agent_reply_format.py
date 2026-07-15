from app.modules.agent.service import _normalize_native_agent_reply


def test_native_agent_reply_hides_internal_citations_and_decorations():
    reply = "## Hadoop ⭐\n\n**HDFS** 负责存储。[chunk_id=852]\n\n✅ 支持分布式存储。"

    cleaned = _normalize_native_agent_reply(reply)

    assert "## Hadoop" in cleaned
    assert "**HDFS**" in cleaned
    assert "chunk_id" not in cleaned
    assert "⭐" not in cleaned
    assert "✅" not in cleaned
