from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from reliability_agent.catalog import FailureCatalog, load_catalog

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "failures.yaml"


def test_load_default_catalog() -> None:
    catalog = load_catalog(CATALOG_PATH)
    assert catalog.diagnoses
    assert catalog.failures
    assert "TRANSCRIPT_MISSING" in catalog.diagnosis_names()
    assert catalog.has_failure("transcript_missing")


def test_get_failure_returns_entry() -> None:
    catalog = load_catalog(CATALOG_PATH)
    failure = catalog.get_failure("transcript_missing")
    assert failure.diagnosis == "TRANSCRIPT_MISSING"
    assert failure.service == "transcribe"


def test_get_failure_unknown_raises() -> None:
    catalog = load_catalog(CATALOG_PATH)
    with pytest.raises(KeyError, match="unknown failure id"):
        catalog.get_failure("does_not_exist")


def test_unknown_diagnosis_rejected(tmp_path: Path) -> None:
    bad = {
        "diagnoses": {
            "PROCESS_DOWN": {
                "failure_class": "SERVICE_AVAILABILITY",
                "description": "down",
            }
        },
        "failures": [
            {
                "id": "bad_row",
                "diagnosis": "NOT_A_REAL_DIAGNOSIS",
                "detection": ["incident"],
            }
        ],
    }
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown diagnosis"):
        load_catalog(path)


def test_duplicate_failure_id_rejected(tmp_path: Path) -> None:
    bad = {
        "diagnoses": {
            "PROCESS_DOWN": {
                "failure_class": "SERVICE_AVAILABILITY",
                "description": "down",
            }
        },
        "failures": [
            {"id": "dup", "diagnosis": "PROCESS_DOWN", "detection": []},
            {"id": "dup", "diagnosis": "PROCESS_DOWN", "detection": []},
        ],
    }
    path = tmp_path / "dup.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate failure id"):
        load_catalog(path)


def test_failures_for_diagnosis() -> None:
    catalog = load_catalog(CATALOG_PATH)
    rows = catalog.failures_for_diagnosis("TRANSCRIPT_MISSING")
    assert {row.id for row in rows} >= {
        "transcript_missing",
        "transcript_missing_db_insert",
    }


def test_agent_actionable_defaults_true(tmp_path: Path) -> None:
    data = {
        "diagnoses": {
            "PROCESS_DOWN": {
                "failure_class": "SERVICE_AVAILABILITY",
                "description": "down",
            }
        },
        "failures": [
            {"id": "svc_down", "diagnosis": "PROCESS_DOWN", "detection": ["poll_class_1"]},
        ],
    }
    path = tmp_path / "ok.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    catalog = FailureCatalog.model_validate(data)
    assert catalog.get_failure("svc_down").agent_actionable is True
