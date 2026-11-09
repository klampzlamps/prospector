"""/prospect command-line tool. Every deterministic step of the workflow lives here.

  import <file> [--limit N] [--area TOWN]  read + filter a scraper export or a list of names, start a run
  area <run> "<town>"             set the town/area for a list of names
  lookup-next / lookup-row / lookup-validate / lookup-apply
                                  find website, address, phone etc. for rows that only have a name
  status [run]                    progress of a run
  next [run] [--max N]            row IDs to hand to researchers now (records an attempt)
  row <run> <ROW_ID>              everything a researcher needs for one business
  scan <run> <ROW_ID> [--url U]   scan the business website (emails, social links, role lines)
  validate <run> [--row ROW_ID]   check research files against the rules
  fb-queue [run]                  rows whose Facebook page needs a logged-in browser
  fb-result <run> <ROW_ID> ...    record what the browser showed on a Facebook page
  build [run]                     write the final spreadsheet (.xlsx + .csv)

  profile [status|init|done]      the user's personal setup (~/.prospect)
  settings [show | set KEY VALUE] personal settings layered over config.json
  li-queue / li-result            optional logged-in LinkedIn lookups (daily limit)
  outreach-queue / outreach-mark  email drafting/sending bookkeeping (daily limit, no double-emailing)
  outreach-status [run]           emails drafted/sent for a run
  dnc <email|@domain>             add to the do-not-contact list
  sheet-data <run> --tab NAME     one chunk of a finished tab as JSON (for the Google Sheets connector)

<run> may be a run folder name, a path, or "latest".
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ (it embeds local folder paths, which would travel with a shared copy)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import emails as em  # noqa: E402
import extras as ex  # noqa: E402
import lookup as lk  # noqa: E402
from builder import build, load_research, research_path  # noqa: E402
from common import (die, eligibility_path, load_config, personalization_path, read_json, rel,  # noqa: E402
                    resolve_run, runs_dir, setup_console, write_json)
from importer import FIELD_LABELS, import_file  # noqa: E402
from rules import validate  # noqa: E402


def load_rows(run_dir):
    return read_json(run_dir / "rows.json")


def find_row(rows_doc, row_id):
    row_id = row_id.strip().upper()
    for r in rows_doc["rows"]:
        if r["row_id"] == row_id:
            return r
    die(f"{row_id} is not a row in this run (it may have been filtered out).")


def state_path(run_dir):
    return run_dir / "state.json"


def load_state(run_dir):
    p = state_path(run_dir)
    return read_json(p) if p.exists() else {"attempts": {}}


def row_status(run_dir, row, cfg):
    d, errors = load_research(run_dir, row, cfg)
    if d is None and errors == ["Not researched yet."]:
        return "pending", errors, None
    if errors:
        return "invalid", errors, d
    return "valid", [], d


# ------------------------------------------------------------------ commands
def cmd_import(a, cfg):
    src = Path(a.file).expanduser()
    if not src.exists():
        die(f"File not found: {src}")
    headers, mapping, records, kept, dropped = import_file(src, cfg)
    limited = 0
    if a.limit and a.limit > 0 and len(kept) > a.limit:
        limited = len(kept) - a.limit
        kept = kept[: a.limit]
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in src.stem)[:40].strip("-") or "run"
    base = runs_dir() / f"{datetime.now():%Y-%m-%d_%H%M}_{stem}"
    run_dir, n = base, 2
    while run_dir.exists():
        run_dir, n = Path(f"{base}_{n}"), n + 1
    (run_dir / "research").mkdir(parents=True)
    lookup_rows = [r for r in kept if r.get("needs_lookup")]
    write_json(run_dir / "rows.json", {
        "version": 1, "run": run_dir.name, "created": datetime.now().isoformat(timespec="seconds"),
        "source_file": src.name, "source_rows": len(records), "mapping": mapping,
        "filters": cfg.get("filters", {}), "limited_out": limited, "rows": kept, "dropped": dropped,
        "area": (a.area or "").strip(), "lookup_pending": bool(lookup_rows),
    })
    with_addr = sum(r["has_address"] for r in kept)
    print(f"RUN: {run_dir.name}")
    print(f"Source: {src.name} - {len(records)} data rows")
    print("Columns detected:")
    for f, label in FIELD_LABELS.items():
        print(f"  {label:<24} <- {mapping[f]!r}" if f in mapping else f"  {label:<24}    (not in file)")
    print(f"Kept: {len(kept)}  (with street address: {with_addr}, service-area/no address: {len(kept) - with_addr})")
    if limited:
        print(f"Limited to the first {a.limit} kept rows (--limit); {limited} more were left out of this run.")
    print(f"Dropped by filters: {len(dropped)}")
    reasons = {}
    for r in dropped:
        reason = r["drop_reason"]
        key = f"Duplicate ({reason.rsplit('(', 1)[-1]}" if reason.startswith("Duplicate") else reason
        reasons[key] = reasons.get(key, 0) + 1
    for k, v in reasons.items():
        print(f"  - {k}: {v}")
    if lookup_rows:
        print(f"LOOKUP NEEDED: {len(lookup_rows)} rows have only a business name. Their website, address, phone and "
              f"category will be looked up first; filters and duplicate checks run again afterwards.")
        no_town = [r for r in lookup_rows if not r.get("city")]
        if no_town and not a.area:
            print(f"AREA: not set - {len(no_town)} names have no town. Ask the user which town/area they're in, "
                  f"then run: area {run_dir.name} \"<town or area>\"  (or skip if the names are distinctive)")
        elif a.area:
            print(f"AREA: {a.area}")
    missing_loc = [r["row_id"] for r in kept if not r["has_address"] and not r["closest_location"]
                   and not r.get("needs_lookup")]
    if missing_loc:
        print(f"Note: {len(missing_loc)} no-address rows have no town in the data; researchers will fill CLOSEST LOCATION.")


def cmd_status(a, cfg, quiet=False):
    run_dir = resolve_run(a.run)
    rows_doc = load_rows(run_dir)
    attempts = load_state(run_dir)["attempts"]
    max_att = cfg.get("research", {}).get("max_attempts_per_row", 3)
    buckets = {"valid": [], "invalid": [], "pending": [], "gave_up": [], "fb": []}
    for r in rows_doc["rows"]:
        st, _, d = row_status(run_dir, r, cfg)
        if st == "valid":
            buckets["valid"].append(r["row_id"])
            if (d.get("facebook") or {}).get("status") == "needs_browser":
                buckets["fb"].append(r["row_id"])
        elif attempts.get(r["row_id"], 0) >= max_att:
            buckets["gave_up"].append(r["row_id"])
        else:
            buckets[st].append(r["row_id"])
    if quiet:
        return run_dir, rows_doc, buckets
    total = len(rows_doc["rows"])
    print(f"RUN: {run_dir.name}   rows to research: {total}   dropped by filters: {len(rows_doc.get('dropped', []))}")
    if rows_doc.get("lookup_pending"):
        n = sum(1 for r in rows_doc["rows"] if r.get("needs_lookup"))
        print(f"  LOOK-UP NOT FINISHED: {n} rows still only have a name (run lookup-next, then lookup-apply)")
    print(f"  Done and passing checks : {len(buckets['valid'])}")
    print(f"    ...of which waiting on a Facebook browser check: {len(buckets['fb'])}")
    print(f"  Failed checks (will retry): {len(buckets['invalid'])}  {' '.join(buckets['invalid'][:20])}")
    print(f"  Not started             : {len(buckets['pending'])}")
    print(f"  Gave up after {max_att} tries   : {len(buckets['gave_up'])}  {' '.join(buckets['gave_up'][:20])}")
    return run_dir, rows_doc, buckets


def cmd_next(a, cfg):
    run_dir = resolve_run(a.run)
    rows_doc = load_rows(run_dir)
    if rows_doc.get("lookup_pending"):
        print("LOOKUP FIRST - some rows only have a name. Run lookup-next until NONE LEFT, then lookup-apply.")
        return 2
    state = load_state(run_dir)
    attempts = state["attempts"]
    max_att = cfg.get("research", {}).get("max_attempts_per_row", 3)
    limit = a.max or cfg.get("research", {}).get("parallel_agents", 8)
    picked, remaining = [], 0
    for r in rows_doc["rows"]:
        st, _, _ = row_status(run_dir, r, cfg)
        if st == "valid" or attempts.get(r["row_id"], 0) >= max_att:
            continue
        if len(picked) < limit:
            picked.append(r["row_id"])
        else:
            remaining += 1
    for rid in picked:
        attempts[rid] = attempts.get(rid, 0) + 1
    write_json(state_path(run_dir), state)
    if not picked:
        gave_up = [r["row_id"] for r in rows_doc["rows"] if row_status(run_dir, r, cfg)[0] != "valid"]
        print("NONE LEFT")
        if gave_up:
            print(f"{len(gave_up)} rows could not pass the checks after {max_att} tries and will be flagged "
                  f"for manual research: {' '.join(gave_up)}")
        return
    print(" ".join(picked))
    print(f"(run {run_dir.name}: {len(picked)} rows now, about {remaining} still waiting after these)")


def cmd_row(a, cfg):
    run_dir = resolve_run(a.run)
    row = find_row(load_rows(run_dir), a.row_id)
    rid = row["row_id"]
    show = lambda label, v: print(f"{label:<22}: {v if v not in (None, '', []) else '-'}")
    print(f"=== {rid}  (row {row['source_row']} of your input file) ===")
    show("Business name", row["business_name"])
    show("Address", row["address"] if row["has_address"] else f"{row['address'] or 'none'}  (service-area business, no street address)")
    if not row["has_address"]:
        show("Closest location", row["closest_location"] or "UNKNOWN - you must fill closest_location")
    show("City/town", row.get("city"))
    show("Phone", row["phone"])
    show("Website", row["website"])
    show("Category", row["category"])
    show("Rating / reviews", f"{row['rating'] or '-'} / {int(row['reviews']) if row['reviews'] else '-'}")
    show("Google Maps", row["maps_url"])
    show("Facebook (scraper)", row.get("facebook"))
    if row.get("listing_url"):
        show("Directory listing", f"{row['listing_url']}  (the scraper's 'website' was this listing, not a real site)")
    show("Emails (scraper)", ", ".join(row["scraper_emails"]) + "  <- leads only: record one only if you see it on a page"
         if row["scraper_emails"] else "")
    show("Search query", row.get("query"))
    if row.get("lookup_sources"):
        show("Details came from", "  ".join(row["lookup_sources"][:3]) + "  (found by the look-up step from the name)")
    if row.get("lookup_note"):
        show("Look-up", row["lookup_note"] + " Find the website yourself first.")
    path = research_path(run_dir, rid)
    print(f"\nELIGIBILITY RULES (Read this): {eligibility_path()}")
    if personalization_path().exists():
        print(f"USER'S PROFILE (Read the 'Who I'm targeting' section for context): {personalization_path()}")
    print(f"\nWRITE YOUR RESEARCH TO: {rel(path)}")
    if path.exists():
        d, errors = load_research(run_dir, row, cfg)
        if not errors:
            print("\nSTATUS: this row already PASSES the checks. Nothing to do - reply with its summary line.")
            return
        print("\nA PREVIOUS ATTEMPT FAILED THESE CHECKS - read the existing file, fix only these, keep everything else:")
        for e in errors:
            print(f"  - {e}")
        return
    template = {
        "row_id": rid,
        "business_name": row["business_name"],
        "trading_status": "",
        "website_url": (row["website"] if "://" in row["website"] else f"https://{row['website']}") if row["website"] else None,
        "closest_location": None,
        "people_seen_on_website": [],
        "contact": {"name": None, "job_title": None, "role_type": None, "source": None, "source_url": None},
        "contact_search": {
            "website": {"outcome": "", "urls": []},
            "google": {"outcome": "", "queries": [], "urls": []},
            "linkedin": {"outcome": "", "queries": [], "urls": []},
        },
        "emails": [],
        "facebook": {"page_url": None, "status": "", "checked_via": "none", "queries": []},
        "google_email_search": {"outcome": "", "queries": []},
        "eligibility": {"status": "", "justification": "", "evidence_urls": []},
        "notes": "",
        "audit_notes": "",
        "action_notes": "",
    }
    print("\nTEMPLATE (fill it in; field rules are in research-brief.md):")
    print(json.dumps(template, indent=2, ensure_ascii=False))


def cmd_scan(a, cfg):
    from site_scan import scan
    run_dir = resolve_run(a.run)
    row = find_row(load_rows(run_dir), a.row_id)
    url = a.url or row["website"]
    if not url:
        die("This row has no website. Pass --url if you found one, otherwise set the website step to skipped_no_website.")
    out_dir = run_dir / "pages" / row["row_id"]
    r = scan(url, out_dir)
    if not r["reachable"]:
        print(f"WEBSITE COULD NOT BE LOADED: {url}  ({r['error']})")
        print("Try WebFetch on it once. If that fails too: keep website_url, set the website step outcome to "
              "not_found with this URL in urls, and say 'Website unreachable' in audit_notes.")
        return
    print(f"Scanned {len(r['pages'])} pages of {r['final_url']}" + ("  (expired SSL certificate)" if r["insecure_ssl"] else ""))
    if r["js_heavy_suspected"]:
        print("NOTE: the homepage has almost no readable text (built with JavaScript). Use WebFetch on the key pages.")
    print("\nEMAILS ON THE SITE (check each belongs to this business - ignore web-designer/plugin addresses):")
    for addr, urls in r["emails"].items():
        print(f"  {addr}   on {urls[0]}")
    if not r["emails"]:
        print("  none found")
    print("\nSOCIAL LINKS:")
    for kind, links in r["social"].items():
        if links:
            print(f"  {kind}: {'  '.join(links[:4])}")
    if not any(r["social"].values()):
        print("  none found")
    print("\nLINES MENTIONING ROLES (owner / founder / director / marketing / manager...):")
    for x in r["role_lines"][:25]:
        print(f"  [{x['url']}] {x['line']}")
    if not r["role_lines"]:
        print("  none")
    print("\nPAGE TEXT SAVED - Read the about/team/contact ones to find names and job titles:")
    for p in r["pages"]:
        print(f"  {rel(p['file'])}   {p['url']}  ({p['chars']} chars) {p['title'][:60]}")


def cmd_validate(a, cfg):
    run_dir = resolve_run(a.run)
    rows_doc = load_rows(run_dir)
    if a.row:
        row = find_row(rows_doc, a.row)
        st, errors, _ = row_status(run_dir, row, cfg)
        if st == "valid":
            print(f"PASS {row['row_id']}")
            return 0
        print(f"FAIL {row['row_id']} - {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    bad = 0
    for row in rows_doc["rows"]:
        st, errors, _ = row_status(run_dir, row, cfg)
        if st != "valid":
            bad += 1
            print(f"{row['row_id']} {st.upper()}: {errors[0]}" + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""))
    print(f"{len(rows_doc['rows']) - bad} of {len(rows_doc['rows'])} rows pass.")
    return 1 if bad else 0


def cmd_fb_queue(a, cfg):
    run_dir, rows_doc, buckets = cmd_status(a, cfg, quiet=True)
    by_id = {r["row_id"]: r for r in rows_doc["rows"]}
    ids = buckets["fb"][: a.max] if a.max else buckets["fb"]
    if not ids:
        print("EMPTY - no Facebook pages need a browser check.")
        return
    for rid in ids:
        r = by_id[rid]
        d = read_json(research_path(run_dir, rid))
        town = r.get("city") or r.get("closest_location") or r.get("address") or ""
        print(f"{rid} | {r['business_name']} | {town} | {d['facebook']['page_url']}")
    if len(buckets["fb"]) > len(ids):
        print(f"(+{len(buckets['fb']) - len(ids)} more after these)")


def cmd_fb_result(a, cfg):
    run_dir = resolve_run(a.run)
    row = find_row(load_rows(run_dir), a.row_id)
    path = research_path(run_dir, row["row_id"])
    if not path.exists():
        die("This row has no research file yet.")
    d = read_json(path)
    fb = d.setdefault("facebook", {})
    url = a.url or fb.get("page_url")

    def note(msg):
        d["audit_notes"] = f"{(d.get('audit_notes') or '').strip()} {msg}".strip()

    if a.status == "login_required":
        print("NOT RECORDED - Facebook is asking to log in. Ask the user to log in to Facebook in the browser.")
        return 3
    if a.status == "checked_email_found":
        addrs = [em.clean(x) for x in (a.email or [])]
        bad = [x for x in addrs if not em.is_valid(x) or em.junk_reason(x)]
        if not addrs or bad:
            die(f"--email needs at least one real address (bad: {bad})")
        contact = (d.get("contact") or {}).get("name") or ""
        existing = {em.clean(e.get("address", "")) for e in d.get("emails", [])}
        for x in addrs:
            if x in existing:
                for e in d["emails"]:
                    if em.clean(e.get("address", "")) == x and e.get("found_on") != "website":
                        e["found_on"], e["source_url"] = "facebook", url
            else:
                kind = em.classify(x, contact, business_name=row["business_name"])
                d.setdefault("emails", []).append({"address": x, "kind": kind, "found_on": "facebook", "source_url": url})
        fb.update({"status": "checked_email_found", "checked_via": "browser", "page_url": url})
    elif a.status == "checked_no_email":
        fb.update({"status": "checked_no_email", "checked_via": "browser", "page_url": url})
    elif a.status in ("wrong_page", "page_not_found"):
        fb.update({"status": "no_page_found", "checked_via": "browser", "page_url": None})
        note("Facebook link found earlier was not this business's page." if a.status == "wrong_page"
             else "Facebook page no longer exists.")
    write_json(path, d)
    errors = validate(row, d, cfg)
    if errors:
        print(f"RECORDED, but {row['row_id']} now fails checks (it will go back to research):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"RECORDED {row['row_id']}: facebook {fb['status']}")
    return 0


def cmd_build(a, cfg):
    run_dir = resolve_run(a.run)
    rows_doc = load_rows(run_dir)
    xlsx_path, csv_paths, s = build(run_dir, rows_doc, cfg)
    print(f"SPREADSHEET: {rel(xlsx_path)}")
    for p in csv_paths:
        print(f"CSV:         {rel(p)}")
    print(f"Tabs: With address {s['with_address_rows']} rows | No address {s['no_address_rows']} rows | "
          f"Filtered out {s['dropped']} rows")
    print(f"Eligibility: Suitable {s['Suitable']} | Review {s['Review']} | Delete {s['Delete']}")
    print(f"Ready to email: {s['ready']}   Have any email: {s['with_email']}   Have a named email: {s['named_email']}   "
          f"Have a contact name: {s['contact']}")
    if s["fb_manual"]:
        print(f"Facebook pages still to check by hand: {s['fb_manual']} (see ACTIONS column)")
    if s["incomplete"]:
        print(f"Rows that failed automatic research (marked Review, see AUDIT NOTES): {s['incomplete']}")


def main():
    setup_console()
    cfg = load_config()
    ap = argparse.ArgumentParser(prog="prospect", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import")
    p.add_argument("file")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--area", default="", help="town/area the businesses are in (helps the name-only look-up)")
    p = sub.add_parser("area")
    p.add_argument("run")
    p.add_argument("area")
    for name in ("lookup-next", "lookup-apply"):
        p = sub.add_parser(name)
        p.add_argument("run", nargs="?", default="latest")
        if name == "lookup-next":
            p.add_argument("--max", type=int, default=0)
    p = sub.add_parser("lookup-row")
    p.add_argument("run")
    p.add_argument("row_id")
    p = sub.add_parser("lookup-validate")
    p.add_argument("run", nargs="?", default="latest")
    p.add_argument("--row")
    for name in ("status", "fb-queue", "build"):
        p = sub.add_parser(name)
        p.add_argument("run", nargs="?", default="latest")
        if name == "fb-queue":
            p.add_argument("--max", type=int, default=0)
    p = sub.add_parser("next")
    p.add_argument("run", nargs="?", default="latest")
    p.add_argument("--max", type=int, default=0)
    p = sub.add_parser("row")
    p.add_argument("run")
    p.add_argument("row_id")
    p = sub.add_parser("scan")
    p.add_argument("run")
    p.add_argument("row_id")
    p.add_argument("--url")
    p = sub.add_parser("validate")
    p.add_argument("run", nargs="?", default="latest")
    p.add_argument("--row")
    p = sub.add_parser("fb-result")
    p.add_argument("run")
    p.add_argument("row_id")
    p.add_argument("--status", required=True,
                   choices=["checked_email_found", "checked_no_email", "login_required", "wrong_page", "page_not_found"])
    p.add_argument("--email", action="append")
    p.add_argument("--url")
    # ---- personal profile + optional extras (LinkedIn, email, Google Sheets)
    p = sub.add_parser("profile")
    p.add_argument("action", nargs="?", default="status", choices=["status", "init", "done"])
    p = sub.add_parser("settings")
    p.add_argument("action", nargs="?", default="show", choices=["show", "set"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p = sub.add_parser("li-queue")
    p.add_argument("run", nargs="?", default="latest")
    p.add_argument("--max", type=int, default=0)
    p = sub.add_parser("li-result")
    p.add_argument("run")
    p.add_argument("row_id")
    p.add_argument("--status", required=True, choices=["found", "not_found", "login_required", "checkpoint"])
    p.add_argument("--name")
    p.add_argument("--title")
    p.add_argument("--role-type", dest="role_type", choices=["marketing", "owner", "senior", "other"])
    p.add_argument("--url")
    p = sub.add_parser("outreach-queue")
    p.add_argument("run", nargs="?", default="latest")
    p.add_argument("--max", type=int, default=10)
    p = sub.add_parser("outreach-mark")
    p.add_argument("run")
    p.add_argument("row_id")
    p.add_argument("--status", required=True, choices=["drafted", "sent", "skipped"])
    p.add_argument("--to")
    p.add_argument("--subject")
    p.add_argument("--id")
    p.add_argument("--reason")
    p = sub.add_parser("outreach-status")
    p.add_argument("run", nargs="?", default="latest")
    p = sub.add_parser("dnc")
    p.add_argument("entry")
    p = sub.add_parser("sheet-data")
    p.add_argument("run")
    p.add_argument("--tab", required=True)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=40)

    a = ap.parse_args()
    handler = {"import": cmd_import, "status": cmd_status, "next": cmd_next, "row": cmd_row, "scan": cmd_scan,
               "validate": cmd_validate, "fb-queue": cmd_fb_queue, "fb-result": cmd_fb_result, "build": cmd_build,
               "profile": ex.cmd_profile, "settings": ex.cmd_settings, "li-queue": ex.cmd_li_queue,
               "li-result": ex.cmd_li_result, "outreach-queue": ex.cmd_outreach_queue,
               "outreach-mark": ex.cmd_outreach_mark, "outreach-status": ex.cmd_outreach_status, "dnc": ex.cmd_dnc,
               "sheet-data": ex.cmd_sheet_data, "area": lk.cmd_area, "lookup-next": lk.cmd_lookup_next,
               "lookup-row": lk.cmd_lookup_row, "lookup-validate": lk.cmd_lookup_validate,
               "lookup-apply": lk.cmd_lookup_apply}
    rc = handler[a.cmd](a, cfg)
    sys.exit(rc if isinstance(rc, int) else 0)


if __name__ == "__main__":
    main()
