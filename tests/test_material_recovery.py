from contextlib import contextmanager
from threading import Event

import pytest

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


def test_material_job_lease_is_renewed_during_long_processing(monkeypatch):
    renewed_in_background = Event()
    calls = 0

    def fake_heartbeat(job_id, worker_id):
        nonlocal calls
        assert (job_id, worker_id) == (17, "worker-a")
        calls += 1
        if calls >= 2:
            renewed_in_background.set()

    monkeypatch.setattr(material_index_job, "_heartbeat", fake_heartbeat)
    monkeypatch.setattr(material_index_job, "LEASE_HEARTBEAT_SECONDS", 0.01)

    with material_index_job._maintain_job_lease(17, "worker-a") as checkpoint:
        checkpoint()
        assert renewed_in_background.wait(timeout=1)

    assert calls >= 2


def test_material_job_lease_surfaces_background_renewal_failure(monkeypatch):
    renewal_failed = Event()
    calls = 0

    def fake_heartbeat(_job_id, _worker_id):
        nonlocal calls
        calls += 1
        if calls >= 2:
            renewal_failed.set()
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(material_index_job, "_heartbeat", fake_heartbeat)
    monkeypatch.setattr(material_index_job, "LEASE_HEARTBEAT_SECONDS", 0.01)

    with pytest.raises(
        material_index_job.MaterialJobLeaseLost,
        match="lease renewal failed",
    ):
        with material_index_job._maintain_job_lease(18, "worker-b") as checkpoint:
            checkpoint()
            assert renewal_failed.wait(timeout=1)


def test_material_job_lease_revalidates_before_successful_exit(monkeypatch):
    monkeypatch.setattr(
        material_index_job,
        "_heartbeat",
        lambda _job_id, _worker_id: (_ for _ in ()).throw(
            material_index_job.MaterialJobLeaseLost("lease reclaimed")
        ),
    )

    with pytest.raises(material_index_job.MaterialJobLeaseLost, match="lease reclaimed"):
        with material_index_job._maintain_job_lease(19, "worker-c"):
            pass


def test_detected_lease_loss_overrides_concurrent_processing_failure(monkeypatch):
    lease_lost = Event()
    calls = 0

    def fake_heartbeat(_job_id, _worker_id):
        nonlocal calls
        calls += 1
        if calls >= 2:
            lease_lost.set()
            raise material_index_job.MaterialJobLeaseLost("lease reclaimed")

    monkeypatch.setattr(material_index_job, "_heartbeat", fake_heartbeat)
    monkeypatch.setattr(material_index_job, "LEASE_HEARTBEAT_SECONDS", 0.01)

    with pytest.raises(material_index_job.MaterialJobLeaseLost, match="lease reclaimed"):
        with material_index_job._maintain_job_lease(20, "worker-d") as checkpoint:
            checkpoint()
            assert lease_lost.wait(timeout=1)
            raise RuntimeError("provider failed at the same time")
