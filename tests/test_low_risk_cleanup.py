import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.integrations.embedding import service as embedding_service
from app.main import STATIC_ROOT
from app.modules.adaptive.schemas import QuestionBankItem
from app.modules.auth.schemas import AuthCredentials
from app.modules.courses.schemas import CourseCreate
from app.modules.materials.schemas import MaterialSearchRequest, TextMaterialCreate


def test_public_string_inputs_are_trimmed_before_validation():
    assert CourseCreate(name="  数据库课程  ", goal="  通过考试  ").model_dump() == {
        "name": "数据库课程",
        "goal": "通过考试",
        "exam_at": None,
        "daily_minutes": 30,
    }
    assert AuthCredentials(username="  learner  ", password="  password-1  ").model_dump() == {
        "username": "learner",
        "password": "password-1",
    }
    assert MaterialSearchRequest(query="  事务隔离  ").query == "事务隔离"
    assert TextMaterialCreate(title="  讲义  ", content="  正文  ").content == "正文"
    assert QuestionBankItem(content="  判断一个网络场景  ", answer="  可以  ").content == "判断一个网络场景"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (CourseCreate, {"name": "   "}),
        (MaterialSearchRequest, {"query": "  "}),
        (TextMaterialCreate, {"title": "标题", "content": "\r\n"}),
        (QuestionBankItem, {"content": "短", "answer": "答案"}),
    ],
)
def test_required_string_inputs_reject_blank_or_too_short_content(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_static_root_is_independent_from_process_working_directory():
    assert STATIC_ROOT.is_absolute()
    assert STATIC_ROOT.name == "static"
    assert (STATIC_ROOT / "vue" / "index.html").is_file()


def test_embedding_model_initialization_is_singleton_under_concurrency(monkeypatch):
    calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_name):
            calls.append(model_name)
            time.sleep(0.03)

    monkeypatch.setattr(embedding_service, "_model", None)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        models = list(executor.map(lambda _: embedding_service.get_embedding_model(), range(8)))

    assert len(calls) == 1
    assert all(model is models[0] for model in models)
