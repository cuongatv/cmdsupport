"""Smoke tests for the opt-in MRP ingestion pipeline."""

import pytest


def test_mrp_module_imports_cleanly():
    """The MRP package must import without side effects."""
    from app.ai.mrp import mapper, merger, pipeline, reducer, verifier, writer

    assert hasattr(pipeline, "run_mrp_pipeline")
    assert hasattr(pipeline, "run_refine_pipeline")
    assert hasattr(pipeline, "get_ingestion_pipeline")
    assert hasattr(pipeline, "normalize_ingestion_pipeline")
    assert hasattr(pipeline, "set_ingestion_pipeline")
    assert hasattr(mapper, "run_map_phase")
    assert hasattr(reducer, "run_reduce_phase")
    assert hasattr(writer, "run_refine_phase")
    assert hasattr(writer, "PageWriteResult")
    assert hasattr(verifier, "run_verify_phase")
    assert hasattr(merger, "merge_page_content")


def test_normalize_ingestion_pipeline_accepts_known_values():
    from app.ai.mrp.pipeline import (
        DEFAULT_INGESTION_PIPELINE,
        normalize_ingestion_pipeline,
    )

    # Default is now MRP — explicit defense against accidental regression.
    assert DEFAULT_INGESTION_PIPELINE == "mrp"
    assert normalize_ingestion_pipeline(None) == "mrp"
    assert normalize_ingestion_pipeline("") == "mrp"
    assert normalize_ingestion_pipeline("legacy") == "legacy"
    assert normalize_ingestion_pipeline("MRP") == "mrp"


def test_normalize_ingestion_pipeline_rejects_unknown_values():
    from app.ai.mrp.pipeline import normalize_ingestion_pipeline

    with pytest.raises(ValueError):
        normalize_ingestion_pipeline("unknown")


def test_set_and_get_ingestion_pipeline_uses_source_metadata():
    from types import SimpleNamespace

    from app.ai.mrp.pipeline import get_ingestion_pipeline, set_ingestion_pipeline

    # Source cũ (metadata None) phải vẫn coi là legacy để tránh re-process.
    source = SimpleNamespace(metadata_=None)
    assert get_ingestion_pipeline(source) == "legacy"

    set_ingestion_pipeline(source, "mrp")
    assert source.metadata_ == {"ingestion_pipeline": "mrp"}
    assert get_ingestion_pipeline(source) == "mrp"

    set_ingestion_pipeline(source, "legacy")
    assert source.metadata_["ingestion_pipeline"] == "legacy"
    assert get_ingestion_pipeline(source) == "legacy"


def test_plan_endpoints_registered_on_app():
    from app.main import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/sources/{source_id}/plan" in paths
    assert "/api/sources/{source_id}/plan/approve" in paths
    assert "/api/sources/{source_id}/plan/reject" in paths
    assert "/api/sources/{source_id}/plan/revise" in paths


def test_worker_registers_new_mrp_tasks():
    from app.worker import WorkerSettings

    function_names = {fn.__name__ for fn in WorkerSettings.functions}
    assert "ingest_map_reduce_task" in function_names
    assert "ingest_refine_task" in function_names
    assert "revise_compilation_plan_task" in function_names
    # Legacy entries are still registered.
    assert "ingest_file_task" in function_names
    assert "ingest_url_task" in function_names


def test_plan_revision_model_present():
    from app.database.models import SourceCompilationPlanRevision

    cols = {col.name for col in SourceCompilationPlanRevision.__table__.columns}
    assert {
        "id",
        "plan_id",
        "source_id",
        "requested_by",
        "feedback",
        "base_version",
        "previous_plan_snapshot",
        "status",
        "error_message",
        "created_at",
        "completed_at",
    }.issubset(cols)
