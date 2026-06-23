"""The audit store is append-only and hash-chained; tampering is detectable."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.audit import record, verify_chain
from app.db.database import Base


def _fresh_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_chain_verifies_then_breaks_on_tamper():
    db = _fresh_session()
    record(db, actor="a", action="threshold.propose", detail="one")
    record(db, actor="b", action="threshold.activate", detail="two")
    record(db, actor="a", action="run.execute", detail="three")
    db.commit()

    assert verify_chain(db)["ok"] is True

    # Tamper with a stored event: the chain must now report a break.
    from app.db.models import AuditEvent
    ev = db.query(AuditEvent).filter(AuditEvent.seq == 2).first()
    ev.detail = "tampered"
    db.commit()

    result = verify_chain(db)
    assert result["ok"] is False
    assert result["broken_at_seq"] == 2
