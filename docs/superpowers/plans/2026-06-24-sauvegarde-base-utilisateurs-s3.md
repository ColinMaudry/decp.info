# Sauvegarde de la base utilisateurs sur S3 — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sauvegarder `users.sqlite` toutes les heures vers un stockage S3-compatible, chiffrée, avec rotation multi-paliers et restauration manuelle.

**Architecture:** Un module `src/backup/` découpé par responsabilité (config, nommage, rotation pure, snapshot SQLite, chiffrement, stockage S3, orchestration, CLI). Un timer systemd lance `python -m src.backup backup` chaque heure. La logique de rétention est une fonction pure testée isolément ; l'orchestration est testée contre un faux stockage en mémoire ; le wrapper S3 réel est testé avec `moto`.

**Tech Stack:** Python 3.10+, `sqlite3` (API de backup en ligne, base en WAL), `gzip`, `cryptography` (Fernet), `boto3` (S3 via `endpoint_url`), `argparse`, `pytest`, `moto[s3]`.

## Global Constraints

- Python : `requires-python >= 3.10`. Pas de syntaxe > 3.10.
- Imports internes toujours préfixés `src.` (ex. `from src.backup import ...`), jamais `backup.` ni `from backup import`.
- La base est ouverte en mode WAL (`src/auth/db.py:49`) → un snapshot DOIT passer par l'API `sqlite3.Connection.backup()`, jamais par une copie de fichier brute.
- CLI : suivre le motif de `src/api/tokens_cli.py` — `def main(argv=None, env=None) -> int`, sous-commandes argparse, `if __name__ == "__main__": sys.exit(main())`.
- Variables d'environnement lues via `os.environ` / argument `env` (jamais d'appel à `load_dotenv()` dans ces modules).
- Tests sous `tests/`, exécutés par `pytest` (`pythonpath = ["src"]`). Commande : `pytest <chemin>`.
- Format de clé S3 (verbatim) : `<prefix>/users-<YYYYMMDDTHHMMSSZ>.sqlite.gz.enc`, horodatage UTC.
- Paliers de rétention (union) : horaire/12 h, 12 h/72 h, quotidien/21 j, mensuel calendaire/12 mois.

---

## Structure des fichiers

| Fichier                          | Responsabilité                                                          |
| -------------------------------- | ----------------------------------------------------------------------- |
| `src/backup/__init__.py`         | Marqueur de package (vide).                                             |
| `src/backup/config.py`           | `BackupConfig` (dataclass) + `load_config(env)`.                        |
| `src/backup/naming.py`           | Construire/parser les clés S3 horodatées.                               |
| `src/backup/rotation.py`         | `select_retained(timestamps, now)` — fonction pure.                     |
| `src/backup/crypto.py`           | `encrypt`/`decrypt` (Fernet).                                           |
| `src/backup/snapshot.py`         | Snapshot SQLite cohérent + gzip ; décompression + contrôle d'intégrité. |
| `src/backup/storage.py`          | `Storage` (Protocol) + `S3Storage` (boto3).                             |
| `src/backup/service.py`          | Orchestration : `run_backup`, `list_backups`, `restore`.                |
| `src/backup/cli.py`              | Point d'entrée argparse.                                                |
| `src/backup/__main__.py`         | Permet `python -m src.backup`.                                          |
| `deploy/decpinfo-backup.service` | Unité systemd oneshot.                                                  |
| `deploy/decpinfo-backup.timer`   | Timer horaire.                                                          |
| `tests/backup/fakes.py`          | `FakeStorage` en mémoire (réutilisé par les tests).                     |
| `tests/backup/test_*.py`         | Tests par module.                                                       |

---

## Task 1: Dépendances + module de configuration

**Files:**

- Modify: `pyproject.toml` (ajout deps `boto3`, `cryptography` ; dev `moto[s3]`)
- Create: `src/backup/__init__.py` (vide)
- Create: `src/backup/config.py`
- Test: `tests/backup/test_config.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  ```python
  @dataclass(frozen=True)
  class BackupConfig:
      db_path: Path
      bucket: str
      prefix: str
      endpoint_url: str | None
      access_key: str
      secret_key: str
      encryption_key: str

  def load_config(env: Mapping[str, str]) -> BackupConfig
  ```

- [ ] **Step 1: Ajouter les dépendances**

Dans `pyproject.toml`, ajouter à la liste `dependencies` (après `"marshmallow>=3.20.0",`) :

```toml
  "boto3",
  "cryptography",
```

Et dans `[dependency-groups]` `dev`, après `"openpyxl",` :

```toml
  "moto[s3]",
```

Puis installer :

```bash
rtk pip install -e . --group=dev
```

- [ ] **Step 2: Écrire le test qui échoue**

Créer `tests/backup/__init__.py` (vide) puis `tests/backup/test_config.py` :

```python
from pathlib import Path

from src.backup.config import BackupConfig, load_config


def test_load_config_reads_env():
    env = {
        "USERS_DB_PATH": "users.sqlite",
        "S3_BUCKET": "decp-backups",
        "S3_BACKUP_PREFIX": "backups",
        "S3_ENDPOINT_URL": "https://s3.example.net",
        "S3_ACCESS_KEY_ID": "AK",
        "S3_SECRET_ACCESS_KEY": "SK",
        "BACKUP_ENCRYPTION_KEY": "key123",
    }
    cfg = load_config(env)
    assert cfg == BackupConfig(
        db_path=Path("users.sqlite"),
        bucket="decp-backups",
        prefix="backups",
        endpoint_url="https://s3.example.net",
        access_key="AK",
        secret_key="SK",
        encryption_key="key123",
    )


def test_load_config_defaults_prefix_and_empty_endpoint():
    env = {
        "USERS_DB_PATH": "users.sqlite",
        "S3_BUCKET": "b",
        "S3_ENDPOINT_URL": "",
        "S3_ACCESS_KEY_ID": "AK",
        "S3_SECRET_ACCESS_KEY": "SK",
        "BACKUP_ENCRYPTION_KEY": "k",
    }
    cfg = load_config(env)
    assert cfg.prefix == "backups"
    assert cfg.endpoint_url is None
```

- [ ] **Step 3: Lancer le test (échec attendu)**

Run: `pytest tests/backup/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.backup'`

- [ ] **Step 4: Implémenter**

Créer `src/backup/__init__.py` vide, puis `src/backup/config.py` :

```python
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BackupConfig:
    db_path: Path
    bucket: str
    prefix: str
    endpoint_url: str | None
    access_key: str
    secret_key: str
    encryption_key: str


def load_config(env: Mapping[str, str]) -> BackupConfig:
    return BackupConfig(
        db_path=Path(env["USERS_DB_PATH"]),
        bucket=env["S3_BUCKET"],
        prefix=env.get("S3_BACKUP_PREFIX", "backups"),
        endpoint_url=env.get("S3_ENDPOINT_URL") or None,
        access_key=env["S3_ACCESS_KEY_ID"],
        secret_key=env["S3_SECRET_ACCESS_KEY"],
        encryption_key=env["BACKUP_ENCRYPTION_KEY"],
    )
```

- [ ] **Step 5: Lancer le test (succès attendu)**

Run: `pytest tests/backup/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/backup/__init__.py src/backup/config.py tests/backup/__init__.py tests/backup/test_config.py
git commit -m "feat(backup): config et dépendances pour la sauvegarde S3"
```

---

## Task 2: Nommage des clés S3

**Files:**

- Create: `src/backup/naming.py`
- Test: `tests/backup/test_naming.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  ```python
  def make_key(prefix: str, ts: datetime) -> str       # "<prefix>/users-<YYYYMMDDTHHMMSSZ>.sqlite.gz.enc"
  def parse_timestamp(key: str) -> datetime            # UTC aware ; lève ValueError si non reconnu
  ```

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/backup/test_naming.py` :

```python
from datetime import datetime, timezone

import pytest

from src.backup.naming import make_key, parse_timestamp


def test_make_key_format():
    ts = datetime(2026, 6, 24, 14, 5, 9, tzinfo=timezone.utc)
    assert make_key("backups", ts) == "backups/users-20260624T140509Z.sqlite.gz.enc"


def test_make_key_strips_trailing_slash():
    ts = datetime(2026, 6, 24, 14, 5, 9, tzinfo=timezone.utc)
    assert make_key("backups/", ts).startswith("backups/users-")


def test_roundtrip():
    ts = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert parse_timestamp(make_key("p", ts)) == ts


def test_parse_rejects_unknown_key():
    with pytest.raises(ValueError):
        parse_timestamp("backups/users.sqlite.bak")
```

- [ ] **Step 2: Lancer le test (échec attendu)**

Run: `pytest tests/backup/test_naming.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.backup.naming'`

- [ ] **Step 3: Implémenter**

Créer `src/backup/naming.py` :

```python
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
```

- [ ] **Step 4: Lancer le test (succès attendu)**

Run: `pytest tests/backup/test_naming.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/backup/naming.py tests/backup/test_naming.py
git commit -m "feat(backup): nommage horodaté des clés S3"
```

---

## Task 3: Rotation (fonction pure)

**Files:**

- Create: `src/backup/rotation.py`
- Test: `tests/backup/test_rotation.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  ```python
  def select_retained(timestamps: Iterable[datetime], now: datetime) -> set[datetime]
  ```

  Les horodatages sont supposés aware UTC. Renvoie le sous-ensemble à CONSERVER.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/backup/test_rotation.py` :

```python
from datetime import datetime, timedelta, timezone

from src.backup.rotation import select_retained

NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_most_recent_always_kept():
    ts = [NOW, NOW - timedelta(hours=2)]
    assert NOW in select_retained(ts, NOW)


def test_recent_hours_kept_by_hourly_tier():
    t = NOW - timedelta(hours=3)
    assert t in select_retained([t], NOW)


def test_two_backups_same_hour_keep_newest():
    older = NOW - timedelta(hours=2, minutes=50)
    newer = NOW - timedelta(hours=2, minutes=10)
    retained = select_retained([older, newer], NOW)
    assert newer in retained
    assert older not in retained


def test_daily_tier_keeps_old_daily_backup():
    t = NOW - timedelta(days=10)
    assert t in select_retained([t], NOW)


def test_monthly_tier_keeps_one_per_calendar_month():
    older = NOW - timedelta(days=40)            # mois M-2 ou M-1 selon calendrier
    same_month_newer = older + timedelta(days=2)
    retained = select_retained([older, same_month_newer], NOW)
    # même mois calendaire -> seul le plus récent du mois est conservé
    assert same_month_newer in retained
    assert older not in retained


def test_keeps_backup_within_12_months():
    t = NOW - timedelta(days=300)
    assert t in select_retained([t], NOW)


def test_drops_backup_older_than_12_months():
    t = NOW - timedelta(days=400)
    assert t not in select_retained([t], NOW)


def test_future_timestamps_ignored():
    t = NOW + timedelta(hours=1)
    assert t not in select_retained([t], NOW)
```

- [ ] **Step 2: Lancer le test (échec attendu)**

Run: `pytest tests/backup/test_rotation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.backup.rotation'`

- [ ] **Step 3: Implémenter**

Créer `src/backup/rotation.py` :

```python
from collections.abc import Iterable
from datetime import datetime, timedelta

# (période, horizon) pour les paliers à période fixe
_FIXED_TIERS = (
    (timedelta(hours=1), timedelta(hours=12)),   # horaire / 12 h
    (timedelta(hours=12), timedelta(hours=72)),  # 12 h / 72 h
    (timedelta(days=1), timedelta(days=21)),     # quotidien / 21 j
)
_MONTHLY_HORIZON = 12  # mois calendaires


def _select_fixed(timestamps, now, period, horizon):
    cutoff = now - horizon
    buckets: dict[int, datetime] = {}
    for t in timestamps:
        if t > now or t < cutoff:
            continue
        idx = int((now - t) // period)
        if idx not in buckets or t > buckets[idx]:
            buckets[idx] = t
    return set(buckets.values())


def _month_index(d: datetime) -> int:
    return d.year * 12 + (d.month - 1)


def _select_monthly(timestamps, now):
    now_idx = _month_index(now)
    buckets: dict[int, datetime] = {}
    for t in timestamps:
        if t > now:
            continue
        idx = _month_index(t)
        if idx > now_idx or now_idx - idx >= _MONTHLY_HORIZON:
            continue
        if idx not in buckets or t > buckets[idx]:
            buckets[idx] = t
    return set(buckets.values())


def select_retained(timestamps: Iterable[datetime], now: datetime) -> set[datetime]:
    items = list(timestamps)
    retained: set[datetime] = set()
    for period, horizon in _FIXED_TIERS:
        retained |= _select_fixed(items, now, period, horizon)
    retained |= _select_monthly(items, now)
    return retained
```

- [ ] **Step 4: Lancer le test (succès attendu)**

Run: `pytest tests/backup/test_rotation.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/backup/rotation.py tests/backup/test_rotation.py
git commit -m "feat(backup): rotation multi-paliers (fonction pure)"
```

---

## Task 4: Chiffrement

**Files:**

- Create: `src/backup/crypto.py`
- Test: `tests/backup/test_crypto.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  ```python
  def encrypt(data: bytes, key: str) -> bytes
  def decrypt(token: bytes, key: str) -> bytes
  ```

  `key` est une clé Fernet urlsafe-base64 (générée par `Fernet.generate_key().decode()`).

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/backup/test_crypto.py` :

```python
import pytest
from cryptography.fernet import Fernet

from src.backup.crypto import decrypt, encrypt


def test_roundtrip():
    key = Fernet.generate_key().decode()
    data = b"contenu de la base sqlite"
    assert decrypt(encrypt(data, key), key) == data


def test_wrong_key_fails():
    data = b"secret"
    token = encrypt(data, Fernet.generate_key().decode())
    with pytest.raises(Exception):
        decrypt(token, Fernet.generate_key().decode())
```

- [ ] **Step 2: Lancer le test (échec attendu)**

Run: `pytest tests/backup/test_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.backup.crypto'`

- [ ] **Step 3: Implémenter**

Créer `src/backup/crypto.py` :

```python
from cryptography.fernet import Fernet


def encrypt(data: bytes, key: str) -> bytes:
    return Fernet(key.encode()).encrypt(data)


def decrypt(token: bytes, key: str) -> bytes:
    return Fernet(key.encode()).decrypt(token)
```

- [ ] **Step 4: Lancer le test (succès attendu)**

Run: `pytest tests/backup/test_crypto.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/backup/crypto.py tests/backup/test_crypto.py
git commit -m "feat(backup): chiffrement Fernet des sauvegardes"
```

---

## Task 5: Snapshot SQLite + intégrité

**Files:**

- Create: `src/backup/snapshot.py`
- Test: `tests/backup/test_snapshot.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  ```python
  def make_snapshot(db_path: Path) -> bytes      # snapshot cohérent gzippé
  def write_snapshot(gzipped: bytes, dest: Path) -> None
  def verify_integrity(db_path: Path) -> bool
  ```

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/backup/test_snapshot.py` :

```python
import sqlite3
from pathlib import Path

from src.backup.snapshot import make_snapshot, verify_integrity, write_snapshot


def _make_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER, val TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b')")
    conn.commit()
    conn.close()


def test_snapshot_roundtrip_preserves_rows(tmp_path):
    src = tmp_path / "users.sqlite"
    _make_db(src)
    gzipped = make_snapshot(src)
    restored = tmp_path / "restored.sqlite"
    write_snapshot(gzipped, restored)
    conn = sqlite3.connect(str(restored))
    rows = conn.execute("SELECT id, val FROM t ORDER BY id").fetchall()
    conn.close()
    assert rows == [(1, "a"), (2, "b")]


def test_verify_integrity_ok(tmp_path):
    src = tmp_path / "users.sqlite"
    _make_db(src)
    assert verify_integrity(src) is True


def test_verify_integrity_detects_corruption(tmp_path):
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"this is not a sqlite database")
    assert verify_integrity(bad) is False
```

- [ ] **Step 2: Lancer le test (échec attendu)**

Run: `pytest tests/backup/test_snapshot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.backup.snapshot'`

- [ ] **Step 3: Implémenter**

Créer `src/backup/snapshot.py` :

```python
import gzip
import sqlite3
import tempfile
from pathlib import Path


def make_snapshot(db_path: Path) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        src = sqlite3.connect(str(db_path))
        try:
            dst = sqlite3.connect(str(tmp_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        return gzip.compress(tmp_path.read_bytes())
    finally:
        tmp_path.unlink(missing_ok=True)


def write_snapshot(gzipped: bytes, dest: Path) -> None:
    dest.write_bytes(gzip.decompress(gzipped))


def verify_integrity(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.DatabaseError:
        return False
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return row is not None and row[0] == "ok"
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()
```

- [ ] **Step 4: Lancer le test (succès attendu)**

Run: `pytest tests/backup/test_snapshot.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/backup/snapshot.py tests/backup/test_snapshot.py
git commit -m "feat(backup): snapshot SQLite cohérent et contrôle d'intégrité"
```

---

## Task 6: Stockage S3

**Files:**

- Create: `src/backup/storage.py`
- Create: `tests/backup/fakes.py`
- Test: `tests/backup/test_storage_s3.py`

**Interfaces:**

- Consumes: `BackupConfig` (Task 1).
- Produces:

  ```python
  class Storage(Protocol):
      def upload_bytes(self, key: str, data: bytes) -> None: ...
      def download_bytes(self, key: str) -> bytes: ...
      def list_keys(self, prefix: str) -> list[str]: ...
      def delete(self, key: str) -> None: ...

  class S3Storage:
      def __init__(self, bucket, endpoint_url, access_key, secret_key, region="us-east-1")
      @classmethod
      def from_config(cls, config: BackupConfig) -> "S3Storage"

  # tests/backup/fakes.py
  class FakeStorage:  # même interface, dict en mémoire
      objects: dict[str, bytes]
  ```

- [ ] **Step 1: Écrire le faux stockage (utilisé par les tests suivants)**

Créer `tests/backup/fakes.py` :

```python
class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload_bytes(self, key, data):
        self.objects[key] = data

    def download_bytes(self, key):
        return self.objects[key]

    def list_keys(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]

    def delete(self, key):
        self.objects.pop(key, None)
```

- [ ] **Step 2: Écrire le test S3 qui échoue**

Créer `tests/backup/test_storage_s3.py` :

```python
import boto3
import pytest
from moto import mock_aws

from src.backup.storage import S3Storage

BUCKET = "decp-backups"


@pytest.fixture
def s3_storage():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield S3Storage(
            bucket=BUCKET,
            endpoint_url=None,
            access_key="testing",
            secret_key="testing",
        )


def test_upload_list_download_delete(s3_storage):
    s3_storage.upload_bytes("backups/a.enc", b"alpha")
    s3_storage.upload_bytes("backups/b.enc", b"beta")
    s3_storage.upload_bytes("autre/c.enc", b"gamma")

    assert set(s3_storage.list_keys("backups/")) == {"backups/a.enc", "backups/b.enc"}
    assert s3_storage.download_bytes("backups/a.enc") == b"alpha"

    s3_storage.delete("backups/a.enc")
    assert s3_storage.list_keys("backups/") == ["backups/b.enc"]
```

- [ ] **Step 3: Lancer le test (échec attendu)**

Run: `pytest tests/backup/test_storage_s3.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.backup.storage'`

- [ ] **Step 4: Implémenter**

Créer `src/backup/storage.py` :

```python
from typing import Protocol

import boto3

from src.backup.config import BackupConfig


class Storage(Protocol):
    def upload_bytes(self, key: str, data: bytes) -> None: ...
    def download_bytes(self, key: str) -> bytes: ...
    def list_keys(self, prefix: str) -> list[str]: ...
    def delete(self, key: str) -> None: ...


class S3Storage:
    def __init__(self, bucket, endpoint_url, access_key, secret_key, region="us-east-1"):
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    @classmethod
    def from_config(cls, config: BackupConfig) -> "S3Storage":
        return cls(
            bucket=config.bucket,
            endpoint_url=config.endpoint_url,
            access_key=config.access_key,
            secret_key=config.secret_key,
        )

    def upload_bytes(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def download_bytes(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
```

- [ ] **Step 5: Lancer le test (succès attendu)**

Run: `pytest tests/backup/test_storage_s3.py -v`
Expected: PASS (1 test)

- [ ] **Step 6: Commit**

```bash
git add src/backup/storage.py tests/backup/fakes.py tests/backup/test_storage_s3.py
git commit -m "feat(backup): wrapper de stockage S3 (boto3) + faux stockage de test"
```

---

## Task 7: Orchestration (service)

**Files:**

- Create: `src/backup/service.py`
- Test: `tests/backup/test_service.py`

**Interfaces:**

- Consumes: `BackupConfig` (T1), `make_key`/`parse_timestamp` (T2), `select_retained` (T3), `encrypt`/`decrypt` (T4), `make_snapshot`/`write_snapshot`/`verify_integrity` (T5), `Storage` (T6).
- Produces:

  ```python
  def run_backup(config: BackupConfig, storage: Storage, now: datetime) -> str         # clé créée
  def list_backups(config: BackupConfig, storage: Storage) -> list[tuple[str, datetime]]  # trié par date
  def restore(config: BackupConfig, storage: Storage, key: str, now: datetime) -> Path  # chemin de la copie de secours
  ```

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/backup/test_service.py` :

```python
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.backup import service
from src.backup.config import BackupConfig
from src.backup.naming import make_key
from tests.backup.fakes import FakeStorage

NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)


def _make_db(path: Path, val: str):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (val TEXT)")
    conn.execute("INSERT INTO t VALUES (?)", (val,))
    conn.commit()
    conn.close()


def _config(db_path: Path) -> BackupConfig:
    return BackupConfig(
        db_path=db_path,
        bucket="b",
        prefix="backups",
        endpoint_url=None,
        access_key="AK",
        secret_key="SK",
        encryption_key=Fernet.generate_key().decode(),
    )


def test_run_backup_uploads_key(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "v1")
    storage = FakeStorage()
    key = service.run_backup(_config(db), storage, NOW)
    assert key in storage.objects
    assert key == "backups/users-20260624T120000Z.sqlite.gz.enc"


def test_run_backup_applies_rotation(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "v1")
    cfg = _config(db)
    storage = FakeStorage()
    # une vieille sauvegarde de >12 mois doit être supprimée par la rotation
    stale = make_key(cfg.prefix, NOW - timedelta(days=400))
    storage.objects[stale] = b"old"
    service.run_backup(cfg, storage, NOW)
    assert stale not in storage.objects


def test_list_backups_sorted(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "v1")
    cfg = _config(db)
    storage = FakeStorage()
    storage.objects[make_key(cfg.prefix, NOW)] = b"x"
    storage.objects[make_key(cfg.prefix, NOW - timedelta(hours=1))] = b"x"
    storage.objects["backups/garbage.txt"] = b"x"  # ignoré
    result = service.list_backups(cfg, storage)
    dates = [ts for _, ts in result]
    assert dates == sorted(dates)
    assert len(result) == 2


def test_restore_replaces_db_and_keeps_safety_copy(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "original")
    cfg = _config(db)
    storage = FakeStorage()
    key = service.run_backup(cfg, storage, NOW)  # sauvegarde "original"

    # la base change ensuite
    db.unlink()
    _make_db(db, "modifie")

    backup_copy = service.restore(cfg, storage, key, NOW)

    conn = sqlite3.connect(str(db))
    val = conn.execute("SELECT val FROM t").fetchone()[0]
    conn.close()
    assert val == "original"
    assert backup_copy.exists()  # copie de secours de la base "modifie"


def test_restore_rejects_corrupt_backup(tmp_path):
    db = tmp_path / "users.sqlite"
    _make_db(db, "original")
    cfg = _config(db)
    storage = FakeStorage()
    from src.backup import crypto
    bad_key = make_key(cfg.prefix, NOW)
    import gzip
    storage.objects[bad_key] = crypto.encrypt(gzip.compress(b"not sqlite"), cfg.encryption_key)
    with pytest.raises(ValueError):
        service.restore(cfg, storage, bad_key, NOW)
```

- [ ] **Step 2: Lancer le test (échec attendu)**

Run: `pytest tests/backup/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.backup.service'`

- [ ] **Step 3: Implémenter**

Créer `src/backup/service.py` :

```python
import os
import tempfile
from datetime import datetime
from pathlib import Path

from src.backup import crypto, naming, snapshot
from src.backup.config import BackupConfig
from src.backup.rotation import select_retained
from src.backup.storage import Storage


def _dated_keys(storage: Storage, prefix: str) -> list[tuple[str, datetime]]:
    dated: list[tuple[str, datetime]] = []
    for key in storage.list_keys(prefix):
        try:
            dated.append((key, naming.parse_timestamp(key)))
        except ValueError:
            continue
    return dated


def run_backup(config: BackupConfig, storage: Storage, now: datetime) -> str:
    data = snapshot.make_snapshot(config.db_path)
    encrypted = crypto.encrypt(data, config.encryption_key)
    key = naming.make_key(config.prefix, now)
    storage.upload_bytes(key, encrypted)

    dated = _dated_keys(storage, config.prefix)
    retained = select_retained((ts for _, ts in dated), now)
    for k, ts in dated:
        if ts not in retained:
            storage.delete(k)
    return key


def list_backups(config: BackupConfig, storage: Storage) -> list[tuple[str, datetime]]:
    dated = _dated_keys(storage, config.prefix)
    dated.sort(key=lambda item: item[1])
    return dated


def restore(config: BackupConfig, storage: Storage, key: str, now: datetime) -> Path:
    encrypted = storage.download_bytes(key)
    data = crypto.decrypt(encrypted, config.encryption_key)

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    snapshot.write_snapshot(data, tmp_path)
    if not snapshot.verify_integrity(tmp_path):
        tmp_path.unlink(missing_ok=True)
        raise ValueError(f"Sauvegarde corrompue, restauration annulée : {key}")

    db_path = config.db_path
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    backup_copy = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    if db_path.exists():
        backup_copy.write_bytes(db_path.read_bytes())
    os.replace(tmp_path, db_path)
    return backup_copy
```

- [ ] **Step 4: Lancer le test (succès attendu)**

Run: `pytest tests/backup/test_service.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/backup/service.py tests/backup/test_service.py
git commit -m "feat(backup): orchestration backup/list/restore"
```

---

## Task 8: CLI

**Files:**

- Create: `src/backup/cli.py`
- Create: `src/backup/__main__.py`
- Test: `tests/backup/test_cli.py`

**Interfaces:**

- Consumes: `load_config` (T1), `service` (T7), `S3Storage` (T6).
- Produces:

  ```python
  def main(argv=None, env=None, storage=None) -> int   # backup | list | restore <key>
  ```

  Si `storage is None`, construit `S3Storage.from_config(config)` (injectable pour les tests).

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/backup/test_cli.py` :

```python
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

from src.backup import cli
from tests.backup.fakes import FakeStorage


def _env(tmp_path: Path) -> dict:
    db = tmp_path / "users.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (val TEXT)")
    conn.execute("INSERT INTO t VALUES ('v1')")
    conn.commit()
    conn.close()
    return {
        "USERS_DB_PATH": str(db),
        "S3_BUCKET": "b",
        "S3_BACKUP_PREFIX": "backups",
        "S3_ENDPOINT_URL": "",
        "S3_ACCESS_KEY_ID": "AK",
        "S3_SECRET_ACCESS_KEY": "SK",
        "BACKUP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    }


def test_backup_then_list(tmp_path, capsys):
    env = _env(tmp_path)
    storage = FakeStorage()
    assert cli.main(["backup"], env=env, storage=storage) == 0
    assert cli.main(["list"], env=env, storage=storage) == 0
    out = capsys.readouterr().out
    assert "users-" in out
    assert len(storage.objects) == 1
```

- [ ] **Step 2: Lancer le test (échec attendu)**

Run: `pytest tests/backup/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.backup.cli'`

- [ ] **Step 3: Implémenter**

Créer `src/backup/cli.py` :

```python
import argparse
import os
import sys
from datetime import datetime, timezone

from src.backup import service
from src.backup.config import load_config
from src.backup.storage import S3Storage


def main(argv=None, env=None, storage=None) -> int:
    env = env if env is not None else os.environ
    parser = argparse.ArgumentParser(prog="python -m src.backup")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup", help="Créer une sauvegarde et appliquer la rotation")
    sub.add_parser("list", help="Lister les sauvegardes disponibles")
    p_restore = sub.add_parser("restore", help="Restaurer une sauvegarde")
    p_restore.add_argument("key", help="Clé S3 de la sauvegarde à restaurer")
    args = parser.parse_args(argv)

    config = load_config(env)
    if storage is None:
        storage = S3Storage.from_config(config)
    now = datetime.now(timezone.utc)

    if args.cmd == "backup":
        key = service.run_backup(config, storage, now)
        print(f"sauvegarde créée : {key}")
        return 0

    if args.cmd == "list":
        backups = service.list_backups(config, storage)
        if not backups:
            print("(aucune sauvegarde)")
            return 0
        for key, ts in backups:
            print(f"{ts.isoformat()}  {key}")
        return 0

    if args.cmd == "restore":
        print("⚠ Arrêtez d'abord le service : systemctl stop decpinfo")
        backup_copy = service.restore(config, storage, args.key, now)
        print(f"restauré depuis : {args.key}")
        print(f"copie de secours de l'ancienne base : {backup_copy}")
        print("Redémarrez ensuite le service : systemctl start decpinfo")
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

Créer `src/backup/__main__.py` :

```python
import sys

from src.backup.cli import main

sys.exit(main())
```

- [ ] **Step 4: Lancer le test (succès attendu)**

Run: `pytest tests/backup/test_cli.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add src/backup/cli.py src/backup/__main__.py tests/backup/test_cli.py
git commit -m "feat(backup): CLI backup/list/restore"
```

---

## Task 9: Déploiement (systemd, env, doc)

**Files:**

- Create: `deploy/decpinfo-backup.service`
- Create: `deploy/decpinfo-backup.timer`
- Modify: `.template.env`
- Modify: `CLAUDE.md` (section déploiement — commandes d'installation du timer)

**Interfaces:**

- Consumes: `python -m src.backup backup` (T8).
- Produces: artefacts de déploiement (pas de test automatisé ; vérification par validation systemd).

- [ ] **Step 1: Variables d'environnement**

Ajouter à la fin de `.template.env` :

```bash
# Sauvegarde de users.sqlite vers un stockage S3-compatible
S3_ENDPOINT_URL=https://s3.exemple.net
S3_BUCKET=decp-backups
S3_BACKUP_PREFIX=backups
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
# Clé Fernet : générer avec
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# À CONSERVER HORS DU SERVEUR : sans elle, les sauvegardes sont irrécupérables.
BACKUP_ENCRYPTION_KEY=
```

- [ ] **Step 2: Unité service systemd**

Créer `deploy/decpinfo-backup.service` :

```ini
[Unit]
Description=Sauvegarde horaire de users.sqlite (decp.info) vers S3
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=decpinfo
WorkingDirectory=/var/www/decpinfo
EnvironmentFile=/var/www/decpinfo/.env
ExecStart=/var/www/decpinfo/.venv/bin/python -m src.backup backup
```

> Adapter `decpinfo` à la valeur réelle de `vars.APP_NAME` si différente, et vérifier que `.env` ne contient que des lignes `CLE=valeur` simples (systemd `EnvironmentFile` ne gère pas `export` ni les variables interpolées).

- [ ] **Step 3: Unité timer systemd**

Créer `deploy/decpinfo-backup.timer` :

```ini
[Unit]
Description=Déclenche la sauvegarde horaire de users.sqlite (decp.info)

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 4: Documenter l'installation**

Dans `CLAUDE.md`, sous `### Deployment`, ajouter :

```markdown
#### Sauvegarde de la base utilisateurs

`users.sqlite` est sauvegardée toutes les heures sur S3 par un timer systemd
(voir `deploy/decpinfo-backup.{service,timer}`). Installation initiale (une fois,
sur le serveur, en root) :

\`\`\`bash
cp deploy/decpinfo-backup.service deploy/decpinfo-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now decpinfo-backup.timer
systemctl list-timers decpinfo-backup.timer # vérifier le prochain déclenchement
\`\`\`

Restauration manuelle :

\`\`\`bash
cd /var/www/decpinfo && source .venv/bin/activate
python -m src.backup list
systemctl stop decpinfo
python -m src.backup restore backups/users-YYYYMMDDTHHMMSSZ.sqlite.gz.enc
systemctl start decpinfo
\`\`\`
```

(Retirer les barres obliques inverses `\` devant les triples accents — elles ne servent qu'à l'échappement dans ce plan.)

- [ ] **Step 5: Vérifier la suite complète**

Run: `pytest tests/backup/ -v`
Expected: PASS (tous les tests des tâches 1-8)

- [ ] **Step 6: Commit**

```bash
git add deploy/decpinfo-backup.service deploy/decpinfo-backup.timer .template.env CLAUDE.md
git commit -m "feat(backup): unités systemd, variables d'env et doc de déploiement"
```

---

## Auto-revue du plan

- **Couverture de la spec :** déclencheur systemd (T9) ✓ ; chiffrement avant upload (T4, intégré T7) ✓ ; snapshot cohérent WAL-safe (T5) ✓ ; 4 paliers de rétention en union (T3) ✓ ; nommage horodaté trié (T2) ✓ ; stockage S3-compatible via endpoint_url (T6) ✓ ; restauration manuelle avec contrôle d'intégrité + copie de secours + remplacement atomique (T7, CLI T8) ✓ ; variables d'env + gestion de la clé (T9) ✓ ; tests unitaires (rotation, crypto, naming) + intégration (snapshot, S3 moto, service, cli) ✓.
- **Placeholders :** aucun « TODO/TBD » ; tout le code et toutes les commandes sont explicites.
- **Cohérence des types :** `make_key(prefix, ts)`/`parse_timestamp(key)`, `select_retained(timestamps, now) -> set`, `encrypt/decrypt(bytes, str) -> bytes`, `make_snapshot(Path) -> bytes` / `write_snapshot(bytes, Path)` / `verify_integrity(Path) -> bool`, interface `Storage` (upload_bytes/download_bytes/list_keys/delete), `run_backup/list_backups/restore` — signatures identiques entre définition (T1-T7) et usage (T7-T8).
