"""Process entrypoint for the Railway worker and local runs."""

from __future__ import annotations

import asyncio
import sys

from vinnytsia_monitor.errors import ConfigError, SessionMissingError, SettingsError
from vinnytsia_monitor.worker import run_worker


def main() -> None:
    if sys.version_info < (3, 12):
        print("Python 3.12 or newer is required.", file=sys.stderr)
        raise SystemExit(1)
    try:
        asyncio.run(run_worker())
    except (SettingsError, ConfigError, SessionMissingError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        raise SystemExit(0) from None
