import re
from datetime import datetime, timezone

_TS_FMT = "%Y%m%dT%H%M%SZ"
_KEY_RE = re.compile(r"users-(\d{8}T\d{6}Z)\.sqlite\.gz\.enc$")


def make_key(prefix: str, ts: datetime) -> str:
    stamp = ts.astimezone(timezone.utc).strftime(_TS_FMT)
    return f"{prefix.rstrip('/')}/users-{stamp}.sqlite.gz.enc"


def parse_timestamp(key: str) -> datetime:
    match = _KEY_RE.search(key)
    if not match:
        raise ValueError(f"clé non reconnue : {key}")
    return datetime.strptime(match.group(1), _TS_FMT).replace(tzinfo=timezone.utc)
