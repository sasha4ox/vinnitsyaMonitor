from pathlib import Path

import pytest

from vinnytsia_monitor.config_load import load_application
from vinnytsia_monitor.errors import ConfigError
from vinnytsia_monitor.pipeline.engine import evaluate
from vinnytsia_monitor.pipeline.models import Label

_CONFIG = """
telegram:
  source_channels:
    - "https://t.me/vin_info_ppo"
  destination_channel: "https://t.me/whynotinukrainian"
runtime:
  dedup_cache_size: 10
  flood_wait_max_seconds: 30
"""

_LOCATIONS = """
locations:
  - id: vinnytsia
    canonical: "Вінниця"
    kind: city
    forms: ["Вінниця", "Вінниці"]
  - id: pysarivka
    canonical: "Писарівка"
    kind: nearby
    forms: ["Писарівка", "Писарівку"]
"""

_RULES = """
require_any_enabled_rule: true
global_excluded_keywords: []
global_excluded_patterns: []
rules:
  - name: City
    enabled: true
    mode: any
    keywords: ["Вінниця"]
    excluded_keywords: ["тест"]
  - name: Both
    enabled: true
    mode: ALL
    keywords: ["Вінниця"]
    patterns: ['(?<!\\w)загроз\\w{0,4}(?!\\w)']
"""

_SAFETY = """
patterns:
  - name: course_toward
    regex: '(?<!\\w)курсом\\s+на(?!\\w)'
"""

_CONTEXT = """
other_region:
  - name: "Жмеринка"
    forms: ["Жмеринка"]
ukraine_general: []
"""

_IGNORE = """
phrases: []
"""


def write_config(directory: Path, **replacements: str) -> Path:
    files = {
        "config.yaml": _CONFIG,
        "locations.yaml": _LOCATIONS,
        "rules.yaml": _RULES,
        "safety.yaml": _SAFETY,
        "context.yaml": _CONTEXT,
        "ignore.yaml": _IGNORE,
    }
    files.update(replacements)
    for name, content in files.items():
        (directory / name).write_text(content.strip() + "\n", encoding="utf-8")
    return directory


def test_shipped_channels_are_distinct(application):
    assert application.source_channels == (
        "https://t.me/vin_info_ppo",
        "https://t.me/vinnytsiarealll",
    )
    assert application.destination_channel == "https://t.me/whynotinukrainian"
    assert len(application.catalog.locations) == 19
    assert application.catalog.safety


def test_rule_level_exclusion_suppresses_only_that_rule(tmp_path):
    catalog = load_application(write_config(tmp_path)).catalog
    decision = evaluate("тест у Вінниці", catalog)

    assert decision.should_forward is False
    assert decision.label is Label.VINNYTSIA_RELEVANT
    assert decision.matched_rules == ()
    assert any("City (тест)" in reason for reason in decision.reasons)


def test_all_mode_requires_every_term(tmp_path):
    catalog = load_application(write_config(tmp_path)).catalog

    assert "Both" in evaluate("загроза у Вінниці", catalog).matched_rules
    assert "Both" not in evaluate("у Вінниці спокійно", catalog).matched_rules
    assert evaluate("у Вінниці спокійно", catalog).should_forward


def test_empty_safety_policy_is_rejected(tmp_path):
    write_config(tmp_path, **{"safety.yaml": "patterns: []\n"})

    with pytest.raises(ConfigError, match="safety.yaml"):
        load_application(tmp_path)


def test_invalid_regex_is_rejected(tmp_path):
    write_config(
        tmp_path,
        **{"safety.yaml": "patterns:\n  - name: broken\n    regex: '(?<!'\n"},
    )

    with pytest.raises(ConfigError, match="regular expression"):
        load_application(tmp_path)


def test_duplicate_place_forms_are_rejected(tmp_path):
    write_config(
        tmp_path,
        **{
            "locations.yaml": """
locations:
  - id: vinnytsia
    canonical: "Вінниця"
    kind: city
    forms: ["Вінниця"]
  - id: alias
    canonical: "Інша"
    kind: nearby
    forms: ["Вінниця"]
"""
        },
    )

    with pytest.raises(ConfigError, match="listed for both"):
        load_application(tmp_path)


def test_destination_cannot_repeat_a_source(tmp_path):
    write_config(
        tmp_path,
        **{
            "config.yaml": """
telegram:
  source_channels: ["https://t.me/vin_info_ppo"]
  destination_channel: "@vin_info_ppo"
"""
        },
    )

    with pytest.raises(ConfigError, match="destination"):
        load_application(tmp_path)
