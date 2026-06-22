"""
config_inventory — device source for the CONFIG intent's INTEGRATED target mode
(CONFIG_INTENT_PLAN.md §10.2).

This is the NEW, separate inventory used by CONFIG, distinct from the MySQL
`inventory` table the SQL/HYBRID flows query. It lives in the SAME MySQL database
(MYSQL_URI) in its own `config_inventory` table.

  • Schema + dummy rows are created idempotently by ensure_schema_and_seed()
    (called on app startup, and runnable standalone: `python -m app.config_inventory`).
  • Credentials are a PLAINTEXT dummy column for the demo only; production replaces
    this with a vault/secret reference. The password is NEVER returned to the client
    (see InventoryDevice.public()) and never written into rendered playbooks/commands.
  • If the DB/table is unavailable, the accessors fall back to an in-memory copy so
    the device picker keeps working in a degraded demo.

The refinement loop reads list_devices()/get_device(); the (future) automated runner
will read the same rows to build a transient Ansible inventory.
"""
from typing import Optional

from sqlalchemy import create_engine, text
from pydantic import BaseModel

from . import logger
from .config import MYSQL_URI


class InventoryDevice(BaseModel):
    device_name: str
    platform: str          # ios / nxos (Cisco IOS for the demo)
    ansible_host: str      # management IP
    username: str
    password: str          # DUMMY only; production -> vault/secret ref
    group: str             # routers / switches

    def public(self) -> dict:
        """Connection info safe to surface (password redacted)."""
        return {
            "device_name": self.device_name,
            "platform": self.platform,
            "ansible_host": self.ansible_host,
            "username": self.username,
            "group": self.group,
        }


# --- DUMMY DATA: seeds the table, and used as a fallback if the DB is unavailable ---
_SEED_DEVICES: list[InventoryDevice] = [
    InventoryDevice(device_name="core-rtr-01",  platform="ios", ansible_host="10.0.0.1", username="netadmin", password="Demo@123", group="routers"),
    InventoryDevice(device_name="edge-rtr-02",  platform="ios", ansible_host="10.0.0.2", username="netadmin", password="Demo@123", group="routers"),
    InventoryDevice(device_name="core-sw-01",   platform="ios", ansible_host="10.0.1.1", username="netadmin", password="Demo@123", group="switches"),
    InventoryDevice(device_name="access-sw-02", platform="ios", ansible_host="10.0.1.2", username="netadmin", password="Demo@123", group="switches"),
    # Test row with a MISSING field (blank username): picking this device in INTEGRATED
    # mode triggers the "complete the missing inventory detail" form. The picker matches
    # on device_name/ansible_host, so a blank username doesn't disturb device selection.
    InventoryDevice(device_name="lab-rtr-09",   platform="ios", ansible_host="10.0.9.9", username="",         password="Demo@123", group="routers"),
]

# `group` is a reserved word in MySQL -> always backtick it.
_CREATE_SQL = text("""
CREATE TABLE IF NOT EXISTS config_inventory (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    device_name  VARCHAR(100) NOT NULL UNIQUE,
    platform     VARCHAR(20)  NOT NULL DEFAULT 'ios',
    ansible_host VARCHAR(64)  NOT NULL,
    username     VARCHAR(64)  NOT NULL,
    password     VARCHAR(128) NOT NULL,
    `group`      VARCHAR(32)  NOT NULL
)
""")

_INSERT_SQL = text("""
    INSERT INTO config_inventory (device_name, platform, ansible_host, username, password, `group`)
    VALUES (:device_name, :platform, :ansible_host, :username, :password, :group)
""")

# create_engine is lazy — it does not open a connection until a query runs.
_engine = create_engine(MYSQL_URI)


def _row_to_device(m) -> InventoryDevice:
    return InventoryDevice(
        device_name=m["device_name"],
        platform=m["platform"],
        ansible_host=m["ansible_host"],
        username=m["username"],
        password=m["password"],
        group=m["group"],
    )


def ensure_schema_and_seed() -> None:
    """Create the table if missing and ensure each dummy device exists. Idempotent, and
    insert-only: a seed device added to _SEED_DEVICES later is inserted on the next run
    even when the table is already populated; existing rows are never overwritten."""
    with _engine.begin() as conn:
        conn.execute(_CREATE_SQL)
        existing = {r[0] for r in conn.execute(text("SELECT device_name FROM config_inventory")).fetchall()}
        added = 0
        for d in _SEED_DEVICES:
            if d.device_name in existing:
                continue
            conn.execute(_INSERT_SQL, d.model_dump())
            added += 1
        if added:
            logger.info("config_inventory: seeded %d new device(s) (%d already present)",
                        added, len(existing))
        else:
            logger.info("config_inventory: all %d seed devices present; nothing to seed",
                        len(_SEED_DEVICES))


def list_devices(group: Optional[str] = None) -> list[InventoryDevice]:
    """Devices for the given target group. 'all'/None returns everything."""
    try:
        with _engine.connect() as conn:
            if not group or group == "all":
                rows = conn.execute(text("SELECT * FROM config_inventory ORDER BY id")).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM config_inventory WHERE `group` = :g ORDER BY id"),
                    {"g": group},
                ).fetchall()
        return [_row_to_device(r._mapping) for r in rows]
    except Exception as exc:
        logger.warning("config_inventory query failed (%s); using in-memory fallback", exc)
        if not group or group == "all":
            return list(_SEED_DEVICES)
        return [d for d in _SEED_DEVICES if d.group == group]


def get_device(device_name: str) -> Optional[InventoryDevice]:
    name = (device_name or "").strip()
    try:
        with _engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM config_inventory WHERE LOWER(device_name) = LOWER(:n)"),
                {"n": name},
            ).fetchone()
        return _row_to_device(row._mapping) if row else None
    except Exception as exc:
        logger.warning("config_inventory lookup failed (%s); using in-memory fallback", exc)
        for d in _SEED_DEVICES:
            if d.device_name.lower() == name.lower():
                return d
        return None


if __name__ == "__main__":
    # Standalone seeding: python -m app.config_inventory
    ensure_schema_and_seed()
    for d in list_devices():
        print(f"{d.device_name:14} {d.ansible_host:10} {d.group}")
