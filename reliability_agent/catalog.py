"""Load and validate failures.yaml — the failure inventory catalog."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "failures.yaml"


class Diagnosis(BaseModel):
    failure_class: str
    description: str


class FailureEntry(BaseModel):
    id: str
    diagnosis: str
    detection: list[str] = Field(default_factory=list)
    service: str | None = None
    stage: str | None = None
    outcome: str | None = None
    dependency: str | None = None
    notes: str | None = None
    agent_actionable: bool = True


class FailureCatalog(BaseModel):
    diagnoses: dict[str, Diagnosis]
    failures: list[FailureEntry]

    @model_validator(mode="after")
    def _validate_catalog(self) -> FailureCatalog:
        if not self.diagnoses:
            raise ValueError("catalog must define at least one diagnosis")
        if not self.failures:
            raise ValueError("catalog must define at least one failure")

        seen_ids: set[str] = set()
        for failure in self.failures:
            if failure.id in seen_ids:
                raise ValueError(f"duplicate failure id: {failure.id}")
            seen_ids.add(failure.id)
            if failure.diagnosis not in self.diagnoses:
                raise ValueError(
                    f"failure {failure.id!r} references unknown diagnosis "
                    f"{failure.diagnosis!r}"
                )
        return self

    def get_failure(self, failure_id: str) -> FailureEntry:
        for failure in self.failures:
            if failure.id == failure_id:
                return failure
        raise KeyError(f"unknown failure id: {failure_id}")

    def has_failure(self, failure_id: str) -> bool:
        return any(failure.id == failure_id for failure in self.failures)

    def get_diagnosis(self, name: str) -> Diagnosis:
        try:
            return self.diagnoses[name]
        except KeyError as exc:
            raise KeyError(f"unknown diagnosis: {name}") from exc

    def diagnosis_names(self) -> list[str]:
        return list(self.diagnoses.keys())

    def failure_ids(self) -> list[str]:
        return [failure.id for failure in self.failures]

    def failures_for_diagnosis(self, diagnosis: str) -> list[FailureEntry]:
        return [failure for failure in self.failures if failure.diagnosis == diagnosis]


def _parse_catalog_raw(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("catalog root must be a mapping")
    diagnoses_raw = data.get("diagnoses")
    failures_raw = data.get("failures")
    if not isinstance(diagnoses_raw, dict):
        raise ValueError("catalog.diagnoses must be a mapping")
    if not isinstance(failures_raw, list):
        raise ValueError("catalog.failures must be a list")
    return {"diagnoses": diagnoses_raw, "failures": failures_raw}


def load_catalog(path: Path | str | None = None) -> FailureCatalog:
    """Load failures.yaml and validate referential integrity."""
    catalog_path = Path(path) if path is not None else DEFAULT_CATALOG_PATH
    with catalog_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return FailureCatalog.model_validate(_parse_catalog_raw(raw))


@lru_cache(maxsize=1)
def get_catalog() -> FailureCatalog:
    """Cached default catalog from repo-root failures.yaml."""
    return load_catalog()
