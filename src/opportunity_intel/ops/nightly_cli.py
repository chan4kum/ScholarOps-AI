"""CLI clock: python -m opportunity_intel.ops.nightly_cli"""

from __future__ import annotations

from opportunity_intel.config import get_settings
from opportunity_intel.db import init_db, session_factory
from opportunity_intel.llm.models_config import load_model_config
from opportunity_intel.ops.nightly import run_nightly_cycle


def main() -> None:
    settings = get_settings()
    init_db(settings)
    session = session_factory()()
    try:
        digest = run_nightly_cycle(
            session,
            settings,
            load_model_config(settings.models_config_path),
        )
        print(digest.message)
    finally:
        session.close()


if __name__ == "__main__":
    main()
