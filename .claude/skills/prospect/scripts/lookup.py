"""Look-up step for rows that only have a business name.

For each name a helper finds the basics a Google Maps scraper would normally give: official name,
website, address, phone, category, rating/reviews (if shown) and whether it is still open. Its file
must pass validate_lookup() (right business, sources recorded, nothing mixed up). lookup-apply then
fills the rows, re-runs the filters and duplicate removal, and unlocks the research step.
"""
import re

from common import die, norm, read_json, rel, resolve_run, text, write_json
from importer import (NOT_A_WEBSITE, apply_filters, clean_website, guess_closest_location, has_street_address,
                      website_domain)

MATCH = ("found", "ambiguous", "not_found")
CLOSED = ("", "temporary", "permanent")
URL_RE = re.compile(r"^https?://[^\s]+\.[^\s]+$", re.I)


def _is_url(v):
    return isinstance(v, str) and bool(URL_RE.match(v.strip()))


def lookup_path(run_dir, row_id):
    return run_dir / "lookup" / f"{row_id}.json"


def area_for(row, rows_doc):
    return row.get("city") or rows_doc.get("area") or ""


def validate_lookup(row, d):
    E = []
    err = E.append
    if not isinstance(d, dict):
        return ["The file must contain one JSON object (use the template from lookup-row)."]
    if d.get("row_id") != row["row_id"]:
        err(f'row_id must be "{row["row_id"]}".')
    if norm(d.get("input_name")) != norm(row["input_name"]):
        err(f'input_name must be exactly "{row["input_name"]}" (copy it from lookup-row).')
    m = d.get("match")
    if m not in MATCH:
        err(f"match must be one of {list(MATCH)}.")
    q = d.get("queries")
    if not isinstance(q, list) or not q:
        err("queries must list the exact searches you ran.")
        q = []
    src = d.get("sources")
    if not isinstance(src, list) or not all(_is_url(u) for u in src):
        err("sources must be a list of full URLs where you saw the details.")
        src = []

    if m == "found":
        if not text(d.get("official_name")):
            err("official_name is required: the business's name as it appears on its website or listing.")
        if not any(text(d.get(k)) for k in ("website", "phone", "address")):
            err("A found business needs at least one of website, phone or address.")
        if not src:
            err("sources must include at least one URL that shows these details.")
        if len(text(d.get("match_evidence"))) < 20:
            err("match_evidence must say in one sentence how you know it's the right business "
                "(e.g. 'Website footer shows the same Leeds address and phone as its Yell listing').")
        w = text(d.get("website"))
        if w:
            if not _is_url(w):
                err("website must be a full URL starting with http(s)://, or \"\" if it has no website of its own.")
            else:
                dom = website_domain(w)
                if any(dom == h or dom.endswith("." + h) for h in NOT_A_WEBSITE):
                    err(f"website is a {dom} page, not the business's own site. Put a Facebook page in 'facebook', "
                        "leave other directory/social links out of 'website' (they can go in sources).")
        p = text(d.get("phone"))
        if p and len(re.sub(r"\D", "", p)) < 7:
            err("phone doesn't look like a phone number.")
        if d.get("closed", "") not in CLOSED:
            err('closed must be "" (open, or unknown), "temporary" or "permanent".')
        r = d.get("rating")
        if r is not None and not (isinstance(r, (int, float)) and 0 <= r <= 5):
            err("rating must be a number from 0 to 5, or null if you didn't see one.")
        rv = d.get("reviews")
        if rv is not None and not (isinstance(rv, int) and rv >= 0):
            err("reviews must be a whole number, or null if you didn't see one.")
        fb = text(d.get("facebook"))
        if fb and not (_is_url(fb) and "facebook.com" in fb.lower()):
            err("facebook must be a full facebook.com URL, or \"\".")
        if not (text(d.get("address")) or text(d.get("town"))):
            err("Give the address, or at least the town it's based in/serves (service-area businesses often "
                "have no public address).")
    elif m == "ambiguous":
        c = d.get("candidates")
        ok = isinstance(c, list) and len(c) >= 2 and all(
            isinstance(x, dict) and text(x.get("name")) and (text(x.get("town")) or text(x.get("address")))
            and _is_url(x.get("url")) for x in c)
        if not ok:
            err("ambiguous needs at least 2 candidates, each with name, town (or address) and url.")
    elif m == "not_found":
        if len(q) < 3:
            err("not_found needs at least 3 different searches listed in queries.")
    return E


def lookup_state(run_dir, row):
    p = lookup_path(run_dir, row["row_id"])
    if not p.exists():
        return "pending", ["Not looked up yet."], None
    try:
        d = read_json(p)
    except Exception as e:
        return "invalid", [f"Not valid JSON: {e}"], None
    errors = validate_lookup(row, d)
    return ("invalid" if errors else "valid"), errors, d


def _lookup_rows(rows_doc):
    return [r for r in rows_doc["rows"] if r.get("needs_lookup")]


# ---------------------------------------------------------------- commands
def cmd_area(a, cfg):
    run_dir = resolve_run(a.run)
    rows_doc = read_json(run_dir / "rows.json")
    rows_doc["area"] = a.area.strip()
    write_json(run_dir / "rows.json", rows_doc)
    print(f"AREA set to '{rows_doc['area']}' for {run_dir.name}.")
    return 0


def cmd_lookup_next(a, cfg):
    run_dir = resolve_run(a.run)
    rows_doc = read_json(run_dir / "rows.json")
    if not rows_doc.get("lookup_pending"):
        print("NOT NEEDED - every row already has its details.")
        return 0
    state_p = run_dir / "state.json"
    state = read_json(state_p) if state_p.exists() else {"attempts": {}}
    att = state.setdefault("lookup_attempts", {})
    max_att = cfg.get("research", {}).get("max_attempts_per_row", 3)
    limit = a.max or cfg.get("research", {}).get("parallel_agents", 8)
    picked, waiting = [], 0
    for r in _lookup_rows(rows_doc):
        st, _, _ = lookup_state(run_dir, r)
        if st == "valid" or att.get(r["row_id"], 0) >= max_att:
            continue
        if len(picked) < limit:
            picked.append(r["row_id"])
        else:
            waiting += 1
    for rid in picked:
        att[rid] = att.get(rid, 0) + 1
    write_json(state_p, state)
    if not picked:
        print("NONE LEFT - now run lookup-apply.")
        return 0
    print(" ".join(picked))
    print(f"({len(picked)} businesses to look up now, about {waiting} waiting after these)")
    return 0


def cmd_lookup_row(a, cfg):
    run_dir = resolve_run(a.run)
    rows_doc = read_json(run_dir / "rows.json")
    row = next((r for r in rows_doc["rows"] if r["row_id"] == a.row_id.strip().upper()), None)
    if not row or not row.get("needs_lookup"):
        die(f"{a.row_id} is not a row that needs looking up.")
    area = area_for(row, rows_doc)
    print(f"=== {row['row_id']} ===")
    print(f"Business name : {row['input_name']}")
    print(f"Area          : {area or 'not given - search without it, and be strict about matching'}")
    if row.get("category"):
        print(f"Category      : {row['category']}")
    path = lookup_path(run_dir, row["row_id"])
    print(f"\nWRITE YOUR LOOKUP TO: {rel(path)}")
    st, errors, _ = lookup_state(run_dir, row)
    if st == "valid":
        print("\nSTATUS: already PASSES. Nothing to do - reply with its summary line.")
        return 0
    if st == "invalid":
        print("\nA PREVIOUS ATTEMPT FAILED THESE CHECKS - read the existing file, fix only these:")
        for e in errors:
            print(f"  - {e}")
        return 0
    import json
    template = {"row_id": row["row_id"], "input_name": row["input_name"], "match": "", "official_name": "",
                "website": "", "address": "", "town": "", "phone": "", "category": row.get("category", ""),
                "rating": None, "reviews": None, "closed": "", "facebook": "", "google_maps_url": "",
                "sources": [], "queries": [], "match_evidence": "", "candidates": [], "notes": ""}
    print("\nTEMPLATE (rules are in lookup-brief.md):")
    print(json.dumps(template, indent=2, ensure_ascii=False))
    return 0


def cmd_lookup_validate(a, cfg):
    run_dir = resolve_run(a.run)
    rows_doc = read_json(run_dir / "rows.json")
    targets = [r for r in _lookup_rows(rows_doc) if not a.row or r["row_id"] == a.row.strip().upper()]
    if a.row and not targets:
        die(f"{a.row} is not a row that needs looking up.")
    bad = 0
    for r in targets:
        st, errors, _ = lookup_state(run_dir, r)
        if st == "valid":
            if a.row:
                print(f"PASS {r['row_id']}")
            continue
        bad += 1
        if a.row:
            print(f"FAIL {r['row_id']} - {len(errors)} problem(s):")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"{r['row_id']} {st.upper()}: {errors[0]}")
    if not a.row:
        print(f"{len(targets) - bad} of {len(targets)} look-ups pass.")
    return 1 if bad else 0


def cmd_lookup_apply(a, cfg):
    run_dir = resolve_run(a.run)
    rows_doc = read_json(run_dir / "rows.json")
    if not rows_doc.get("lookup_pending"):
        print("NOT NEEDED - look-ups were already applied.")
        return 0
    state_p = run_dir / "state.json"
    att = (read_json(state_p) if state_p.exists() else {}).get("lookup_attempts", {})
    max_att = cfg.get("research", {}).get("max_attempts_per_row", 3)
    unfinished = [r["row_id"] for r in _lookup_rows(rows_doc)
                  if lookup_state(run_dir, r)[0] != "valid" and att.get(r["row_id"], 0) < max_att]
    if unfinished:
        print(f"NOT FINISHED - {len(unfinished)} look-ups still to do ({' '.join(unfinished[:15])}). Run lookup-next.")
        return 1

    kept, dropped = [], list(rows_doc.get("dropped", []))
    counts = {"found": 0, "ambiguous": 0, "not_found": 0, "failed": 0}
    for r in rows_doc["rows"]:
        if not r.get("needs_lookup"):
            kept.append(r)
            continue
        st, _, d = lookup_state(run_dir, r)
        if st != "valid":
            counts["failed"] += 1
            r["lookup_note"] = "Automatic look-up failed; research will try from the name alone."
            r["needs_lookup"] = False
            if not r.get("city") and rows_doc.get("area"):
                r["closest_location"] = r.get("closest_location") or rows_doc["area"]
            kept.append(r)
            continue
        counts[d["match"]] += 1
        if d["match"] == "ambiguous":
            cands = "; ".join(f"{c['name']} ({text(c.get('town')) or text(c.get('address'))})" for c in d["candidates"][:4])
            r["drop_reason"] = f"Several businesses match this name - add a town and re-run: {cands}"
            dropped.append(r)
            continue
        if d["match"] == "not_found":
            r["drop_reason"] = "Couldn't find this business online"
            dropped.append(r)
            continue
        # found: fill only what's empty - never overwrite details the user supplied
        r["business_name"] = text(d.get("official_name")) or r["business_name"]
        for field, key in (("address", "address"), ("phone", "phone"), ("category", "category"),
                           ("facebook", "facebook"), ("maps_url", "google_maps_url")):
            if not text(r.get(field)) and text(d.get(key)):
                r[field] = text(d.get(key))
        if not r.get("website") and text(d.get("website")):
            r["website"] = clean_website(d["website"])
        if not r.get("city"):
            r["city"] = text(d.get("town")) or rows_doc.get("area", "")
        if r.get("rating") is None and d.get("rating") is not None:
            r["rating"] = float(d["rating"])
        if r.get("reviews") is None and d.get("reviews") is not None:
            r["reviews"] = float(d["reviews"])
        if d.get("closed"):
            r["closed"] = d["closed"]
        r["has_address"] = has_street_address(r["address"])
        r["closest_location"] = "" if r["has_address"] else guess_closest_location(r["city"], r["address"], r.get("query", ""))
        r["lookup_sources"] = [u for u in d.get("sources", []) if _is_url(u)]
        r["needs_lookup"] = False
        kept.append(r)

    # Now the details are known, run the same filters and duplicate checks as a scraper file gets.
    still, newly_dropped = apply_filters(kept, cfg.get("filters", {}))
    dropped += newly_dropped
    # keep the Filtered out tab in original file order
    dropped.sort(key=lambda r: r["row_id"])
    rows_doc["rows"], rows_doc["dropped"], rows_doc["lookup_pending"] = still, dropped, False
    write_json(run_dir / "rows.json", rows_doc)
    print(f"LOOK-UP APPLIED to {run_dir.name}")
    print(f"  Found: {counts['found']}   Several possible matches (dropped): {counts['ambiguous']}   "
          f"Not found (dropped): {counts['not_found']}   Look-up failed (kept for research): {counts['failed']}")
    if newly_dropped:
        reasons = {}
        for r in newly_dropped:
            reason = r["drop_reason"]
            k = f"Duplicate ({reason.rsplit('(', 1)[-1]}" if reason.startswith("Duplicate") else reason
            reasons[k] = reasons.get(k, 0) + 1
        print("  Removed by your filters now the details are known: " + ", ".join(f"{k}: {v}" for k, v in reasons.items()))
    with_addr = sum(r["has_address"] for r in still)
    print(f"Ready for research: {len(still)} businesses (with street address: {with_addr}, service-area: {len(still) - with_addr})")
    return 0
