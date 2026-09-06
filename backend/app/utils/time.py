from datetime import datetime


def utcnow() -> datetime:
    """Naive UTC "now", matching how SQLite round-trips DateTime columns
    (SQLAlchemy's sqlite dialect always returns naive datetimes on read back,
    so mixing in timezone-aware values causes "can't subtract offset-naive
    and offset-aware datetimes"). Keep every datetime in this app naive UTC.
    """
    return datetime.utcnow()
