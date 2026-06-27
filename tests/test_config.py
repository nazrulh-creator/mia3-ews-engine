"""Visualisation-tier configuration flags (persistence + cache)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.services import appsettings


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, future=True)()


def test_viz_flags_default_set_and_persist():
    db = _db()
    try:
        appsettings.load_cache(db)
        assert appsettings.viz_flags().all is True   # default all on

        appsettings.set_viz_flags(db, actor="tester", tier1=True, tier2=False, tier3=False)
        db.commit()
        assert appsettings.viz_flags().tier2 is False
        assert appsettings.viz_flags().all is False
        assert appsettings.viz_flags().any is True

        appsettings.load_cache(db)                   # reload from DB → persisted
        assert appsettings.viz_flags().tier2 is False
        assert appsettings.viz_flags().tier1 is True
    finally:
        # cache is process-global; restore all-on so other tests are unaffected.
        appsettings.set_viz_flags(db, actor="tester", tier1=True, tier2=True, tier3=True)
        db.commit()
