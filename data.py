"""
Persistence layer.

On Streamlit Cloud  →  reads/writes a private GitHub Gist (JSON).
Locally             →  falls back to timeline_data.json on disk.

Required Streamlit secrets (set in the Cloud dashboard or .streamlit/secrets.toml):
    [gist]
    token   = "github_pat_..."   # GitHub PAT with 'gist' scope
    gist_id = "abc123..."        # ID of the private Gist
"""
import json
import os
from datetime import date, timedelta

import requests
import streamlit as st

# ── Local fallback path ───────────────────────────────────────────────────────
_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_FILE  = os.path.join(_DIR, "timeline_data.json")
LOCK_FILE  = DATA_FILE + ".lock"
GIST_FILENAME = "timeline_data.json"

# ── Detect which backend to use ───────────────────────────────────────────────
def _gist_cfg() -> tuple[str, str] | None:
    """Return (token, gist_id) if Gist secrets are configured, else None."""
    try:
        token   = st.secrets["gist"]["token"]
        gist_id = st.secrets["gist"]["gist_id"]
        if token and gist_id:
            return token, gist_id
    except Exception:
        pass
    return None

DEFAULT_DATA = {
    "project_name": "My Project",
    "team_name": "Team Alpha",
    "start_date": "2026-04-01",   # YYYY-MM-DD
    "num_iterations": 12,
    "members": ["Alice", "Bob", "Charlie", "Diana"],
    # tasks keyed by  "owner::iter_num::slot"  (owner = member name or "__team__")
    # slot = 0,1,2
    "tasks": {}
}


def _gist_load(token: str, gist_id: str) -> dict:
    """Fetch the JSON content of the Gist."""
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    r = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers, timeout=10)
    r.raise_for_status()
    content = r.json()["files"][GIST_FILENAME]["content"]
    return json.loads(content)


def _gist_save(token: str, gist_id: str, data: dict):
    """Write JSON back to the Gist (PATCH is not atomic, but GitHub handles concurrent
    requests gracefully — last write wins per field, which is fine for this use case)."""
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    payload = {"files": {GIST_FILENAME: {"content": json.dumps(data, indent=2, ensure_ascii=False)}}}
    r = requests.patch(f"https://api.github.com/gists/{gist_id}", headers=headers,
                       json=payload, timeout=10)
    r.raise_for_status()


def _local_load() -> dict:
    from filelock import FileLock
    with FileLock(LOCK_FILE, timeout=5):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def _local_save(data: dict):
    from filelock import FileLock
    with FileLock(LOCK_FILE, timeout=5):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
        else:
            on_disk = dict(DEFAULT_DATA)
        for k in DEFAULT_DATA:
            if k != "tasks":
                on_disk[k] = data[k]
        on_disk.setdefault("tasks", {})
        on_disk["tasks"].update(data["tasks"])
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(on_disk, f, indent=2, ensure_ascii=False)


def _migrate(data: dict) -> dict:
    """Back-fill missing keys and migrate old field names."""
    for k, v in DEFAULT_DATA.items():
        data.setdefault(k, v)
    if "start_month" in data and "start_date" not in data:
        data["start_date"] = data.pop("start_month") + "-01"
    if "num_months" in data and "num_iterations" not in data:
        data["num_iterations"] = data.pop("num_months") * 2
    return data


def load() -> dict:
    cfg = _gist_cfg()
    try:
        if cfg:
            token, gist_id = cfg
            raw = _gist_load(token, gist_id)
        else:
            raw = _local_load()
    except Exception:
        raw = {}
    return _migrate(raw if raw else dict(DEFAULT_DATA))


def save(data: dict):
    """Merge-save: updates tasks key-by-key so concurrent saves don't drop each other."""
    cfg = _gist_cfg()
    if cfg:
        token, gist_id = cfg
        try:
            on_gist = _gist_load(token, gist_id)
        except Exception:
            on_gist = dict(DEFAULT_DATA)
        for k in DEFAULT_DATA:
            if k != "tasks":
                on_gist[k] = data[k]
        on_gist.setdefault("tasks", {})
        on_gist["tasks"].update(data["tasks"])
        _gist_save(token, gist_id, on_gist)
    else:
        _local_save(data)


def save_full(data: dict):
    """Full replace-save: writes the entire data dict as-is, no merging.
    Use this for resets and config-only saves where you want a clean overwrite."""
    cfg = _gist_cfg()
    if cfg:
        token, gist_id = cfg
        _gist_save(token, gist_id, data)
    else:
        with FileLock(LOCK_FILE, timeout=5):
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)


# ── Iteration helpers ─────────────────────────────────────────────────────────
WEEKS_PER_ITER = 2


def get_iterations(start_date: str, num_iterations: int) -> list[dict]:
    """Return list of dicts with keys: num, label, start, end, date_range"""
    year, month, day = map(int, start_date.split("-"))
    current = date(year, month, day)

    iters = []
    for n in range(1, num_iterations + 1):
        iter_end = current + timedelta(days=13)
        iters.append({
            "num": n,
            "label": f"Iter {n}",
            "start": current.strftime("%Y-%m-%d"),
            "end": iter_end.strftime("%Y-%m-%d"),
            "date_range": f"{current.strftime('%d %b')} – {iter_end.strftime('%d %b %Y')}",
        })
        current += timedelta(weeks=WEEKS_PER_ITER)
    return iters


def task_key(owner: str, iter_num: int, slot: int) -> str:
    return f"{owner}::{iter_num}::{slot}"


def get_task(data: dict, owner: str, iter_num: int, slot: int) -> dict:
    key = task_key(owner, iter_num, slot)
    return data["tasks"].get(key, {
        "feature": "", "descr": "", "ac": "", "sp": "", "iter": iter_num
    })


def set_task(data: dict, owner: str, iter_num: int, slot: int, task: dict):
    key = task_key(owner, iter_num, slot)
    if any(v for v in task.values() if str(v).strip()):
        data["tasks"][key] = task
    else:
        data["tasks"].pop(key, None)


def get_team_task_sp_sum(data: dict, iter_num: int) -> int:
    """Sum SP that each member has entered for the team task (slot 0) of this iteration."""
    total = 0
    for member in data["members"]:
        t = get_task(data, member, iter_num, 0)
        try:
            total += int(str(t.get("sp", "")).strip())
        except (ValueError, TypeError):
            pass
    return total


def get_all_features(data: dict) -> list[str]:
    """Return sorted list of unique non-empty feature names across all tasks."""
    features: set[str] = set()
    for task in data["tasks"].values():
        f = str(task.get("feature", "")).strip()
        if f:
            features.add(f)
    return sorted(features)


TEAM_OWNER = "__team__"


def get_slot_count(data: dict, owner: str, iter_num: int) -> int:
    """Number of slots to show for an owner+iteration: filled tasks + 1 empty add-slot.
    For members, slot 0 is always the team-task mirror so personal tasks start at slot 1."""
    start_slot = 1 if (owner != TEAM_OWNER) else 0
    filled = sum(
        1 for slot in range(start_slot, 50)
        if task_key(owner, iter_num, slot) in data["tasks"]
    )
    return start_slot + filled + 1  # +1 for the ＋ slot


def get_next_slot(data: dict, owner: str, iter_num: int) -> int:
    """Return the first free slot index for an owner in a given iteration."""
    start_slot = 1 if (owner != TEAM_OWNER) else 0
    slot = start_slot
    while task_key(owner, iter_num, slot) in data["tasks"]:
        slot += 1
    return slot


def get_iter_col_count(data: dict, iter_num: int, members: list[str]) -> int:
    """Max slot count across team + all members for one iteration (so columns align)."""
    owners = [TEAM_OWNER] + members
    return max(get_slot_count(data, o, iter_num) for o in owners)


