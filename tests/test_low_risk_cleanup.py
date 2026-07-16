import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.integrations.embedding import service as embedding_service
from app.main import STATIC_ROOT
from app.modules.agent.schemas import AgentChatRequest, ChatSessionCreate
from app.modules.auth.schemas import AuthCredentials
from app.modules.courses.schemas import CourseCreate
from app.modules.learning.schemas import LearningAnswer
from app.modules.materials.schemas import MaterialSearchRequest, TextMaterialCreate
from app.modules.resources.schemas import ExternalResourceSearchRequest


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
    assert AgentChatRequest(message="  请讲解索引  ").message == "请讲解索引"
    assert ChatSessionCreate(title="  复习会话  ").title == "复习会话"
    assert LearningAnswer(question_id=1, user_answer="  我的答案  ").user_answer == "我的答案"
    assert MaterialSearchRequest(query="  事务隔离  ").query == "事务隔离"
    assert TextMaterialCreate(title="  讲义  ", content="  正文  ").content == "正文"
    assert ExternalResourceSearchRequest(topic="  边界值  ").topic == "边界值"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (CourseCreate, {"name": "   "}),
        (AgentChatRequest, {"message": "\n\t"}),
        (LearningAnswer, {"question_id": 1, "user_answer": "  "}),
        (MaterialSearchRequest, {"query": "  "}),
        (TextMaterialCreate, {"title": "标题", "content": "\r\n"}),
        (ExternalResourceSearchRequest, {"topic": "  "}),
    ],
)
def test_required_string_inputs_reject_blank_content(model, payload):
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
