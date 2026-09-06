"""Loads config.yaml and resolves project paths.

Single place for the tunables (D15): a threshold is a query parameter, so
changing one here recomputes history rather than migrating it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Thresholds:
    stale_days: int
    ghosted_days: int
    recalibrate_after_responses: int
    cv_max_pages: int = 1


@dataclass(frozen=True)
class Detector:
    claim_min_n: int
    hop_min_n: int
    dead_channel_min_n: int
    response_grace_days: int


@dataclass(frozen=True)
class Followup:
    max_touches_per_company: int
    min_days_between: int
    stop_after_rejection: bool


@dataclass(frozen=True)
class Config:
    data: Path
    templates: Path
    thresholds: Thresholds
    detector: Detector
    followup: Followup
    factgate_allow: tuple[str, ...]
    agent_model: str | None

    @property
    def master_profile(self) -> Path:
        return self.data / "master-profile.yaml"

    @property
    def logs(self) -> Path:
        return self.data / "logs"

    applications_override: Path | None = None

    @property
    def applications(self) -> Path:
        """Where application folders live.

        `tailor-cv` owns them while it is the thing producing CVs (D73), so
        this can point outside the repository.
        """
        return self.applications_override or self.data / "applications"


def _resolve(value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else ROOT / p


@lru_cache(maxsize=1)
def load(path: Path | None = None) -> Config:
    raw = yaml.safe_load((path or ROOT / "config.yaml").read_text())
    paths = raw["paths"]
    # JAM_DATA_DIR wins so a test or a sandbox can point elsewhere.
    data = _resolve(os.environ.get("JAM_DATA_DIR") or paths["data"])
    return Config(
        data=data,
        templates=_resolve(paths["templates"]),
        thresholds=Thresholds(**raw["thresholds"]),
        detector=Detector(**raw["detector"]),
        followup=Followup(**raw["followup"]),
        factgate_allow=tuple(raw.get("factgate", {}).get("allow", [])),
        agent_model=(raw.get("agent") or {}).get("model"),
        applications_override=(_resolve(paths["applications"])
                               if paths.get("applications") else None),
    )
