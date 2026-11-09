"""Shared helpers for the /prospect skill scripts (paths, config, JSON IO, text cleaning)."""
import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config.json"


def setup_console():
    """Windows consoles default to cp1252; force UTF-8 so business names never crash a print."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def project_root() -> Path:
    return Path(os.environ.get("PROSPECT_HOME") or os.getcwd()).resolve()


def runs_dir() -> Path:
    return project_root() / "runs"


def output_dir() -> Path:
    return project_root() / "output"


def die(msg: str, code: int = 2):
    print(f"ERROR: {msg}")
    sys.exit(code)


def load_defaults() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die(f"Missing config file: {CONFIG_PATH}")
    except json.JSONDecodeError as e:
        die(f"config.json is not valid JSON ({e}). Fix {CONFIG_PATH}")


# ---------------------------------------------------------------- the user's personal profile
# Lives in the user's home folder, never inside the skill or project, so sharing either never
# shares anyone's personal details.
def profile_dir() -> Path:
    return Path(os.environ.get("PROSPECT_PROFILE_DIR") or (Path.home() / ".prospect")).resolve()


def settings_path() -> Path:
    return profile_dir() / "settings.json"


def personalization_path() -> Path:
    return profile_dir() / "personalization.md"


def eligibility_path() -> Path:
    """The user's own eligibility rules if setup created them, otherwise the skill's starter rules."""
    mine = profile_dir() / "eligibility.md"
    return mine if mine.exists() else SKILL_DIR / "eligibility.md"


def load_user_settings() -> dict:
    p = settings_path()
    if not p.exists():
        return {}
    try:
        return read_json(p)
    except json.JSONDecodeError as e:
        die(f"Your settings file is not valid JSON ({e}). Fix or delete {p}")


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    """Skill defaults (config.json) with the user's personal settings layered on top."""
    return deep_merge(load_defaults(), load_user_settings())


def usage_path() -> Path:
    return profile_dir() / "usage.json"


def usage_today(kind: str) -> int:
    from datetime import date
    p = usage_path()
    data = read_json(p) if p.exists() else {}
    return int(data.get(date.today().isoformat(), {}).get(kind, 0))


def add_usage(kind: str, n: int = 1):
    from datetime import date, timedelta
    p = usage_path()
    data = read_json(p) if p.exists() else {}
    today = date.today().isoformat()
    data.setdefault(today, {})
    data[today][kind] = int(data[today].get(kind, 0)) + n
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    write_json(p, {d: v for d, v in data.items() if d >= cutoff})


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    """Atomic write so a crash mid-write never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def resolve_run(arg) -> Path:
    """Accept a run folder path, a run folder name, or 'latest'."""
    if arg in (None, "", "latest"):
        rd = runs_dir()
        runs = sorted(p for p in rd.iterdir() if (p / "rows.json").exists()) if rd.exists() else []
        if not runs:
            die(f"No runs found in {rd}")
        return runs[-1].resolve()
    p = Path(arg)
    for cand in (p, runs_dir() / arg):
        if (cand / "rows.json").exists():
            return cand.resolve()
    die(f"Run not found: {arg} (looked in {runs_dir()})")


def rel(path) -> str:
    try:
        return str(Path(path).resolve().relative_to(project_root())).replace("\\", "/")
    except ValueError:
        return str(path)


def text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def norm(s) -> str:
    """Lowercase alphanumerics only - for loose comparisons of names/headers."""
    return re.sub(r"[^a-z0-9]", "", text(s).lower())
