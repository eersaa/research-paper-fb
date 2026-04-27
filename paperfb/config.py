from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml


@dataclass(frozen=True)
class ModelsConfig:
    default: str
    classification: str
    profile_creation: str
    reviewer: str
    judge: str


@dataclass(frozen=True)
class ReviewersConfig:
    count: int
    core_focuses: list[str]
    secondary_focus_per_reviewer: bool
    diversity: str
    seed: Optional[int]


@dataclass(frozen=True)
class ClassificationConfig:
    max_classes: int


@dataclass(frozen=True)
class PathsConfig:
    acm_ccs: str
    reviews_dir: str
    output: str
    logs_dir: str


@dataclass(frozen=True)
class AxesConfig:
    stances: list[str]
    focuses: list[str]


@dataclass(frozen=True)
class Config:
    transport: str
    base_url_env: str
    models: ModelsConfig
    reviewers: ReviewersConfig
    classification: ClassificationConfig
    paths: PathsConfig
    axes: AxesConfig


def load_config(default_path: Path, axes_path: Path) -> Config:
    with default_path.open() as f:
        d = yaml.safe_load(f)
    with axes_path.open() as f:
        a = yaml.safe_load(f)

    reviewers_count = d["reviewers"]["count"]
    if reviewers_count < 3:
        raise ValueError("reviewers.count must be >= 3")

    axes = AxesConfig(stances=a["stances"], focuses=a["focuses"])
    core = d["reviewers"]["core_focuses"]
    for f in core:
        if f not in axes.focuses:
            raise ValueError(f"core focus '{f}' not in axes.focuses")

    return Config(
        transport=d["transport"],
        base_url_env=d["base_url_env"],
        models=ModelsConfig(**d["models"]),
        reviewers=ReviewersConfig(**d["reviewers"]),
        classification=ClassificationConfig(**d["classification"]),
        paths=PathsConfig(**d["paths"]),
        axes=axes,
    )
