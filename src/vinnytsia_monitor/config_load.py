"""Load and validate the YAML configuration directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from vinnytsia_monitor.catalog import Catalog, compile_catalog
from vinnytsia_monitor.channels import channel_key
from vinnytsia_monitor.config_models import AppFile, ContextFile, IgnoreFile, LocationsFile, RulesFile, SafetyFile
from vinnytsia_monitor.errors import ConfigError

_FILES = {
    "config.yaml": AppFile,
    "locations.yaml": LocationsFile,
    "rules.yaml": RulesFile,
    "safety.yaml": SafetyFile,
    "context.yaml": ContextFile,
    "ignore.yaml": IgnoreFile,
}


@dataclass(frozen=True)
class Application:
    source_channels: tuple[str, ...]
    destination_channel: str
    dedup_cache_size: int
    flood_wait_max_seconds: int
    catalog: Catalog


def load_application(config_dir: Path) -> Application:
    if not config_dir.is_dir():
        raise ConfigError(f"Configuration directory does not exist: {config_dir}")

    parsed = {name: _read_model(config_dir / name, model) for name, model in _FILES.items()}
    app_file = parsed["config.yaml"]
    _assert_distinct_destination(app_file.telegram.source_channels, app_file.telegram.destination_channel)
    catalog = compile_catalog(
        parsed["locations.yaml"],
        parsed["rules.yaml"],
        parsed["safety.yaml"],
        parsed["context.yaml"],
        parsed["ignore.yaml"],
    )
    runtime = app_file.runtime
    return Application(
        source_channels=tuple(app_file.telegram.source_channels),
        destination_channel=app_file.telegram.destination_channel,
        dedup_cache_size=runtime.dedup_cache_size,
        flood_wait_max_seconds=runtime.flood_wait_max_seconds,
        catalog=catalog,
    )


def _read_model(path: Path, model: type):
    if not path.is_file():
        raise ConfigError(f"Missing configuration file: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must contain a mapping at the top level")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid {path.name}: {exc}") from exc


def _assert_distinct_destination(sources: list[str], destination: str) -> None:
    destination_key = channel_key(destination)
    for source in sources:
        if channel_key(source) == destination_key:
            raise ConfigError("The destination channel cannot also be a source channel")
