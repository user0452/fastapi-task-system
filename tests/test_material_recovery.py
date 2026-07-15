from contextlib import contextmanager

from app.jobs import material_index_job


def test_pending_material_jobs_are_resumed_on_startup(monkeypatch):
    class Cursor:
        def execute(self, _sql):
            return None

        def fetchall(self):
            return [{"id": 11, "user_id": 2}, {"id": 12, "user_id": 3}]

    @contextmanager
    def fake_cursor():
        yield Cursor()

    resumed = []
    monkeypatch.setattr(material_index_job, "get_cursor", fake_cursor)
    monkeypatch.setattr(
        material_index_job,
        "run_material_processing_job",
        lambda user_id, material_id: resumed.append((user_id, material_id)),
    )

    count = material_index_job.recover_pending_material_jobs()

    assert count == 2
    assert resumed == [(2, 11), (3, 12)]
