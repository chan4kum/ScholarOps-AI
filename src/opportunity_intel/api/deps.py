from collections.abc import Generator

from sqlalchemy.orm import Session

from opportunity_intel.db import session_factory


def get_db() -> Generator[Session, None, None]:
    db = session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
