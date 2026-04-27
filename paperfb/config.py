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
class AxisItem:
    name: str
    description: str


@dataclass(frozen=True)
class AxesConfig:
    stances: list[AxisItem]
    focuses: list[AxisItem]


@dataclass(frozen=True)
class Config:
    transport: str
    base_url_env: str
    models: ModelsConfig
    reviewers: ReviewersConfig
    classification: ClassificationConfig
    paths: PathsConfig
    axes: AxesConfig


def _parse_axis_items(raw: list, axis_name: str) -> list[AxisItem]:
    items: list[AxisItem] = []
    for entry in raw:
        if not isinstance(entry, dict) or "name" not in entry or "description" not in entry:
            raise ValueError(
                f"axes.{axis_name} entries must be {{name, description}} dicts; got {entry!r}"
            )
        items.append(AxisItem(name=entry["name"], description=entry["description"]))
    return items


def load_config(default_path: Path, axes_path: Path) -> Config:
    with default_path.open() as f:
        d = yaml.safe_load(f)
    with axes_path.open() as f:
        a = yaml.safe_load(f)

    reviewers_count = d["reviewers"]["count"]
    if reviewers_count < 3:
        raise ValueError("reviewers.count must be >= 3")

    axes = AxesConfig(
        stances=_parse_axis_items(a["stances"], "stances"),
        focuses=_parse_axis_items(a["focuses"], "focuses"),
    )
    focus_names = {f.name for f in axes.focuses}
    core = d["reviewers"]["core_focuses"]
    for f in core:
        if f not in focus_names:
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
