"""Personal profile, settings, LinkedIn lookups, email outreach and Google Sheets export.

Everything personal is stored in the user's home folder (~/.prospect by default):
  personalization.md   answers from the setup interview (read by the AI)
  settings.json        personal overrides of config.json (read by the scripts)
  eligibility.md       the user's own Suitable/Review/Delete rules
  usage.json           daily counters (LinkedIn lookups, emails) to enforce daily limits
  contacted.json       every address ever drafted/sent, so nobody is emailed twice
  do-not-contact.txt   addresses or domains that must never be emailed (unsubscribes)
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

import emails as em
from builder import load_research, research_path, split_emails
from common import (SKILL_DIR, add_usage, die, eligibility_path, load_defaults, load_user_settings,
                    personalization_path, profile_dir, read_json, rel, resolve_run, settings_path, text,
                    usage_today, write_json)
from rules import validate


def _rows(run_dir):
    return read_json(run_dir / "rows.json")


def _find(rows_doc, row_id):
    row_id = row_id.strip().upper()
    for r in rows_doc["rows"]:
        if r["row_id"] == row_id:
            return r
    die(f"{row_id} is not a row in this run.")


def _on(v):
    return v is True or str(v).lower() in ("true", "yes", "on", "1")


# ================================================================ profile + settings
def cmd_profile(a, cfg):
    d = profile_dir()
    if a.action == "init":
        d.mkdir(parents=True, exist_ok=True)
        if not personalization_path().exists():
            shutil.copy(SKILL_DIR / "personalization-template.md", personalization_path())
        mine = d / "eligibility.md"
        if not mine.exists():
            shutil.copy(SKILL_DIR / "eligibility.md", mine)
        if not settings_path().exists():
            write_json(settings_path(), {})
        dnc = d / "do-not-contact.txt"
        if not dnc.exists():
            dnc.write_text("# One email address or @domain per line. These are never emailed.\n", encoding="utf-8")
        print(f"PROFILE FOLDER: {d}")
        print(f"  personalization: {personalization_path()}")
        print(f"  eligibility rules: {mine}")
        print(f"  settings: {settings_path()}")
        print(f"  do-not-contact list: {dnc}")
        return 0
    if a.action == "done":
        _set_setting("setup.completed", True)
        _set_setting("setup.completed_on", datetime.now().strftime("%Y-%m-%d"))
        print("Setup marked complete.")
        return 0
    # status
    s = cfg
    done = _on(s.get("setup", {}).get("completed"))
    print(f"SETUP: {'complete' if done else 'NOT DONE'}" +
          (f" (on {s['setup'].get('completed_on')})" if done and s['setup'].get('completed_on') else ""))
    print(f"Profile folder      : {d}{'' if d.exists() else '  (not created yet)'}")
    print(f"Personalization file: {personalization_path() if personalization_path().exists() else 'missing'}")
    print(f"Eligibility rules   : {eligibility_path()}")
    b = s.get("browser", {})
    print(f"Browser             : {b.get('name', 'none')}   Facebook checks: {'on' if _on(b.get('facebook_checks')) else 'off'}")
    li = s.get("linkedin", {})
    if _on(li.get("browser_lookups")):
        left = max(0, int(li.get("daily_limit", 25)) - usage_today("linkedin"))
        print(f"LinkedIn lookups    : on (logged-in browser), {left} of {li.get('daily_limit')} left today")
    else:
        print("LinkedIn lookups    : off (contacts found through Google searches of LinkedIn only)")
    o = s.get("outreach", {})
    mode = o.get("mode", "off")
    if mode != "off":
        left = max(0, int(o.get("daily_limit", 30)) - usage_today("emails"))
        print(f"Emails              : {mode} mode, {left} of {o.get('daily_limit')} left today")
    else:
        print("Emails              : off")
    sh = s.get("sheets", {})
    print(f"Google Sheets       : {sh.get('mode', 'manual')}" +
          (f" -> {sh.get('spreadsheet_url')}" if sh.get("mode") == "connector" and sh.get("spreadsheet_url") else ""))
    return 0


def _set_setting(dotted, value):
    defaults = load_defaults()
    keys = dotted.split(".")
    node = defaults
    for k in keys[:-1]:
        if not isinstance(node.get(k), dict):
            die(f"Unknown setting '{dotted}'. Run `settings show` to see the names.")
        node = node[k]
    if keys[-1] not in node and keys[0] not in ("input_columns", "filters", "output", "emails"):
        die(f"Unknown setting '{dotted}'. Run `settings show` to see the names.")
    user = load_user_settings()
    cur = user
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value
    profile_dir().mkdir(parents=True, exist_ok=True)
    write_json(settings_path(), user)


def cmd_settings(a, cfg):
    if a.action == "set":
        if not a.key or a.value is None:
            die('usage: settings set <name> <value>   e.g. settings set filters.min_reviews 5')
        try:
            value = json.loads(a.value)
        except json.JSONDecodeError:
            value = a.value
        _set_setting(a.key, value)
        print(f"SAVED {a.key} = {json.dumps(value, ensure_ascii=False)}  (in {settings_path()})")
        return 0
    def strip(d):
        return {k: strip(v) if isinstance(v, dict) else v for k, v in d.items() if not k.startswith("_")}
    print(json.dumps(strip(cfg), indent=2, ensure_ascii=False))
    return 0


# ================================================================ LinkedIn (logged-in browser)
def cmd_li_queue(a, cfg):
    li = cfg.get("linkedin", {})
    if not _on(li.get("browser_lookups")):
        print("DISABLED - LinkedIn browser lookups are off (turn on in setup).")
        return 0
    left = max(0, int(li.get("daily_limit", 25)) - usage_today("linkedin"))
    if left == 0:
        print(f"LIMIT REACHED - {li.get('daily_limit')} LinkedIn lookups already done today. Try again tomorrow.")
        return 0
    run_dir = resolve_run(a.run)
    rows_doc = _rows(run_dir)
    out = []
    for r in rows_doc["rows"]:
        d, errors = load_research(run_dir, r, cfg)
        if errors or d.get("trading_status") == "closed" or d.get("linkedin_browser_checked"):
            continue
        outcomes = [(d.get("contact_search", {}).get(s) or {}).get("outcome") for s in ("website", "google", "linkedin")]
        if "found_priority" in outcomes:
            continue
        out.append(r)
    limit = min(left, a.max or left)
    if not out:
        print("EMPTY - every business already has a marketing/owner contact or was checked.")
        return 0
    for r in out[:limit]:
        town = r.get("city") or r.get("closest_location") or r.get("address") or ""
        print(f"{r['row_id']} | {r['business_name']} | {town} | {r.get('website') or '-'}")
    if len(out) > limit:
        print(f"(+{len(out) - limit} more; {left} lookups left today)")
    return 0


def cmd_li_result(a, cfg):
    if a.status in ("login_required", "checkpoint"):
        msg = "LinkedIn is asking to log in" if a.status == "login_required" else \
            "LinkedIn showed a security check / CAPTCHA"
        print(f"NOT RECORDED - {msg}. Stop LinkedIn lookups and tell the user.")
        return 3
    run_dir = resolve_run(a.run)
    row = _find(_rows(run_dir), a.row_id)
    path = research_path(run_dir, row["row_id"])
    d = read_json(path)
    cs = d.setdefault("contact_search", {})
    step = cs.setdefault("linkedin", {"outcome": "not_found", "queries": [], "urls": []})
    step.setdefault("queries", []).append(f'LinkedIn people search (logged in): "{row["business_name"]}"')
    note = ""
    if a.status == "found":
        if not (a.name and a.title and a.url and a.role_type):
            die("--status found needs --name, --title, --role-type and --url")
        priority = a.role_type in ("marketing", "owner")
        contact = d.get("contact") or {}
        if priority:
            d["contact"] = {"name": a.name, "job_title": a.title, "role_type": a.role_type, "source": "linkedin",
                            "source_url": a.url}
            step["outcome"] = "found_priority"
            step.setdefault("urls", []).append(a.url)
        elif not contact.get("name"):
            d["contact"] = {"name": a.name, "job_title": a.title, "role_type": a.role_type, "source": "linkedin",
                            "source_url": a.url}
            step["outcome"] = "found_other"
            step.setdefault("urls", []).append(a.url)
        else:
            note = "LinkedIn (logged in) showed only non-marketing/owner staff."
    else:
        note = "LinkedIn (logged in) also checked - no one found."
    if note:
        d["audit_notes"] = f"{text(d.get('audit_notes'))} {note}".strip()
    d["linkedin_browser_checked"] = True
    write_json(path, d)
    add_usage("linkedin")
    errors = validate(row, d, cfg)
    if errors:
        print(f"RECORDED, but {row['row_id']} now fails checks (it will go back to research):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"RECORDED {row['row_id']}: {a.status}" + (f" - {a.name} ({a.title})" if a.status == 'found' else ""))
    return 0


# ================================================================ email outreach
def _contacted_path():
    return profile_dir() / "contacted.json"


def _dnc():
    p = profile_dir() / "do-not-contact.txt"
    if not p.exists():
        return set()
    return {ln.strip().lower() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}


def _blocked(addr, dnc):
    addr = addr.lower()
    return addr in dnc or ("@" + addr.split("@")[-1]) in dnc


def _outreach_log(run_dir):
    p = run_dir / "outreach.json"
    return read_json(p) if p.exists() else {}


def cmd_outreach_queue(a, cfg):
    o = cfg.get("outreach", {})
    if o.get("mode", "off") == "off":
        print("DISABLED - email writing is off (turn it on in setup).")
        return 0
    left = max(0, int(o.get("daily_limit", 30)) - usage_today("emails"))
    if left == 0:
        print(f"LIMIT REACHED - {o.get('daily_limit')} emails already drafted/sent today. Try again tomorrow.")
        return 0
    run_dir = resolve_run(a.run)
    rows_doc = _rows(run_dir)
    log = _outreach_log(run_dir)
    contacted = read_json(_contacted_path()) if _contacted_path().exists() else {}
    dnc = _dnc()
    allowed = set(o.get("only_eligibility") or ["Suitable"])
    extra = cfg.get("emails", {}).get("extra_generic_prefixes", [])
    picked, skipped = [], {"not eligible": 0, "no email": 0, "already emailed": 0, "do-not-contact": 0}
    for r in rows_doc["rows"]:
        if r["row_id"] in log:
            continue
        d, errors = load_research(run_dir, r, cfg)
        if errors or (d.get("eligibility") or {}).get("status") not in allowed:
            skipped["not eligible"] += 1
            continue
        generic, named = split_emails(d, extra)
        order = (named + generic) if o.get("prefer", "named") == "named" else (generic + named)
        order = [x for x in order if not _blocked(x, dnc)]
        if not (generic or named):
            skipped["no email"] += 1
            continue
        if not order:
            skipped["do-not-contact"] += 1
            continue
        to = next((x for x in order if x not in contacted), None)
        if not to:
            skipped["already emailed"] += 1
            continue
        c = d.get("contact") or {}
        first = None
        if to in named and c.get("name"):
            toks = em._name_tokens(c["name"])
            if toks and em.classify(to, c["name"]) == "named" and toks[0] in to.split("@")[0]:
                first = c["name"].split()[0]
        picked.append({
            "row_id": r["row_id"], "business_name": r["business_name"], "to": to, "greeting_name": first,
            "contact_name": c.get("name"), "job_title": c.get("job_title"), "category": r.get("category"),
            "town": r.get("city") or r.get("closest_location") or r.get("address") or "",
            "website": r.get("website") or d.get("website_url"),
            "notes": text(d.get("notes")), "eligibility_justification": text((d.get("eligibility") or {}).get("justification")),
        })
        if len(picked) >= min(left, a.max or left):
            break
    if not picked:
        print("EMPTY - nothing left to email in this run." +
              (" Skipped: " + ", ".join(f"{k} {v}" for k, v in skipped.items() if v) if any(skipped.values()) else ""))
        return 0
    print(f"MODE: {o.get('mode')}   {len(picked)} emails in this batch   {left} left today")
    for p in picked:
        print(json.dumps(p, ensure_ascii=False))
    return 0


def cmd_outreach_mark(a, cfg):
    run_dir = resolve_run(a.run)
    row = _find(_rows(run_dir), a.row_id)
    to = em.clean(a.to or "")
    if a.status in ("drafted", "sent") and not em.is_valid(to):
        die("--to must be the email address used.")
    log = _outreach_log(run_dir)
    log[row["row_id"]] = {"status": a.status, "to": to, "subject": a.subject or "", "id": a.id or "",
                          "reason": a.reason or "", "at": datetime.now().isoformat(timespec="seconds")}
    write_json(run_dir / "outreach.json", log)
    if a.status in ("drafted", "sent"):
        add_usage("emails")
        cp = _contacted_path()
        contacted = read_json(cp) if cp.exists() else {}
        contacted[to] = {"business": row["business_name"], "run": run_dir.name, "status": a.status,
                         "date": datetime.now().strftime("%Y-%m-%d")}
        write_json(cp, contacted)
    print(f"RECORDED {row['row_id']}: {a.status} {to}")
    return 0


def cmd_outreach_status(a, cfg):
    run_dir = resolve_run(a.run)
    log = _outreach_log(run_dir)
    counts = {}
    for v in log.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    o = cfg.get("outreach", {})
    left = max(0, int(o.get("daily_limit", 30)) - usage_today("emails"))
    print(f"RUN {run_dir.name}: " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "no emails yet") +
          f"   |   {left} of {o.get('daily_limit')} left today ({o.get('mode', 'off')} mode)")
    return 0


def cmd_dnc(a, cfg):
    p = profile_dir() / "do-not-contact.txt"
    profile_dir().mkdir(parents=True, exist_ok=True)
    entry = a.entry.strip().lower()
    if not (em.is_valid(entry) or (entry.startswith("@") and "." in entry)):
        die("Give an email address (name@example.com) or a whole domain (@example.com).")
    existing = _dnc()
    if entry not in existing:
        with open(p, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    print(f"ADDED {entry} to the do-not-contact list ({p})")
    return 0


# ================================================================ Google Sheets export
def cmd_sheet_data(a, cfg):
    """Print one chunk of a finished tab as JSON, for writing into Google Sheets with the connector."""
    from builder import build_tabs
    run_dir = resolve_run(a.run)
    tabs = build_tabs(run_dir, _rows(run_dir), cfg)
    names = [t[0] for t in tabs]
    if a.tab not in names:
        die(f"--tab must be one of {names}")
    name, headers, rows = next(t for t in tabs if t[0] == a.tab)
    chunk = rows[a.offset: a.offset + a.limit]
    print(json.dumps({"tab": f"{name} ({run_dir.name[:15]})", "total_rows": len(rows), "offset": a.offset,
                      "first_sheet_row": a.offset + 2, "headers": headers if a.offset == 0 else None,
                      "rows": chunk, "next_offset": a.offset + len(chunk) if a.offset + len(chunk) < len(rows) else None},
                     ensure_ascii=False))
    return 0
