from pathlib import Path

import pytest

from vinnytsia_monitor.config_load import load_application

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def application():
    return load_application(ROOT / "config")


@pytest.fixture(scope="session")
def catalog(application):
    return application.catalog
