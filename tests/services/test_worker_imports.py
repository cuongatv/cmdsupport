import importlib

from app.jobs.telegram_jobs import send_pending_telegram_outbox


def test_worker_settings_import_clean() -> None:
    worker = importlib.import_module("app.worker")

    assert send_pending_telegram_outbox in worker.WorkerSettings.functions


def test_worker_cron_includes_telegram() -> None:
    worker = importlib.import_module("app.worker")

    cron_jobs = getattr(worker.WorkerSettings, "cron_jobs", None)
    if cron_jobs is None:
        return

    assert any(
        send_pending_telegram_outbox.__name__ in repr(job)
        for job in cron_jobs
    )
