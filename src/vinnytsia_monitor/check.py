"""Classify one message locally, without connecting to Telegram."""

from __future__ import annotations

import sys

from vinnytsia_monitor.config_load import load_application
from vinnytsia_monitor.errors import ConfigError
from vinnytsia_monitor.pipeline.engine import evaluate
from vinnytsia_monitor.settings import resolve_config_dir


def main() -> None:
    try:
        text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
        application = load_application(resolve_config_dir())
        decision = evaluate(text, application.catalog)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    sys.stdout.write(decision.render() + "\n")


if __name__ == "__main__":
    main()
