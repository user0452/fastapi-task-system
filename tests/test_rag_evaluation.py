import json
import zipfile

from app.evaluation.rag import (
    aggregate_results,
    deterministic_embeddings,
    evaluate_bundle,
    load_bundle,
    prepare_cases,
    score_case,
)


def _bundle(tmp_path):
    path = tmp_path / "rag-pack.zip"
    corpus = """# Knowledge

### Alpha
**KB-ID：YQ-ALPHA-001**

Alpha uses port 7443.

### Beta
**KB-ID：YQ-BETA-002**

Beta requires restore verification.
"""
    rows = [
        {
            "id": "Q1",
            "type": "fact",
            "question": "Which port does Alpha use?",
            "answer": "7443",
            "supporting_kb_ids": ["YQ-ALPHA-001"],
            "difficulty": "easy",
            "confuser": "",
        }
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("corpus.md", corpus)
        archive.writestr("eval.jsonl", "\n".join(json.dumps(row) for row in rows))
        archive.writestr("README.txt", "not indexed")
    return path


def test_bundle_loader_keeps_corpus_and_gold_separate(tmp_path):
    corpus, rows, metadata = load_bundle(_bundle(tmp_path))

    assert "YQ-ALPHA-001" in corpus
    assert rows[0]["answer"] == "7443"
    assert metadata["corpus_entry"] == "corpus.md"


def test_case_metrics_measure_partial_and_all_support():
    case = {
        "id": "Q",
        "type": "multi_hop",
        "difficulty": "hard",
        "question": "question",
        "supporting_kb_ids": ["YQ-A", "YQ-B"],
    }
    result = score_case(
        case,
        [{"id": 1, "kb_ids": ["YQ-A"], "score": 1, "dense_score": 1, "keyword_score": 1}],
        3.0,
    )
    summary = aggregate_results([result])

    assert result["support_recall"] == 0.5
    assert result["any_hit"] is True
    assert result["all_support_hit"] is False
    assert summary["mean_support_recall"] == 0.5
    assert summary["mrr"] == 1.0


def test_reasoning_mode_deduplicates_and_removes_direct_answer_ids():
    rows = [
        {
            "id": "A",
            "type": "case_reasoning",
            "question": "same",
            "supporting_kb_ids": ["YQ-CASE-001", "YQ-SYS-001"],
        },
        {
            "id": "B",
            "type": "case_reasoning",
            "question": "same",
            "supporting_kb_ids": ["YQ-CASE-002", "YQ-SYS-002"],
        },
    ]

    prepared, stats = prepare_cases(rows, "reasoning")

    assert len(prepared) == 1
    assert prepared[0]["supporting_kb_ids"] == ["YQ-SYS-001"]
    assert stats["deduplicated"] == 1


def test_evaluate_bundle_runs_offline_with_deterministic_embeddings(tmp_path):
    report = evaluate_bundle(
        _bundle(tmp_path),
        top_k=2,
        embedding_provider=deterministic_embeddings,
        embedding_label="test-mock",
    )

    assert report["evaluated_cases"] == 1
    assert report["index"]["unique_kb_ids"] == 2
    assert report["metrics"]["any_hit_rate"] == 1.0
