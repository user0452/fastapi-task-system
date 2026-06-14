import numpy as np
import faiss
from sentence_transformers import SentenceTransformer


_model = None


def get_embedding_model():
    """
    懒加载 embedding 模型。
    第一次调用时加载，后面复用，避免每次请求都重新加载模型。
    """
    global _model

    if _model is None:
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    return _model


def split_text_to_chunks(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    """
    把长文本切成多个 chunk。
    chunk_size：每块大约多少字
    overlap：相邻 chunk 重叠多少字，防止上下文断裂
    """
    text = (text or "").strip()

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - overlap

        if start < 0:
            start = 0

        if start >= len(text):
            break

    return chunks


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    把文本列表转成 embedding 向量矩阵。
    返回 shape 大概是：
    [文本数量, 向量维度]
    """
    model = get_embedding_model()

    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    return embeddings.astype("float32")


def search_similar_chunks(
        query: str,
        chunks: list[dict],
        top_k: int = 5
) -> list[dict]:
    """
    使用 FAISS 从 chunks 中检索与 query 最相似的片段。

    chunks 格式：
    [
        {
            "id": 1,
            "chunk_text": "...",
            "course_name": "...",
            "material_id": 1
        }
    ]
    """
    if not query or not chunks:
        return []

    texts = [item["chunk_text"] for item in chunks]

    chunk_embeddings = embed_texts(texts)
    query_embedding = embed_texts([query])

    dim = chunk_embeddings.shape[1]

    index = faiss.IndexFlatIP(dim)
    index.add(chunk_embeddings)

    scores, indices = index.search(query_embedding, min(top_k, len(chunks)))

    results = []

    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue

        item = chunks[int(idx)].copy()
        item["score"] = float(score)
        results.append(item)

    return results

