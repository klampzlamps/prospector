"""Final step: turn validated research into the spreadsheet.

The builder - not the AI - decides what goes in every cell, so the column order, row order and
formatting are identical every run. Rows are written in the order of the original scraper file.
"""
import csv
from pathlib import Path

import emails as em
from common import output_dir, read_json, text
from rules import validate
from xlsx import write_xlsx

STEP_LABEL = {
    "found_priority": "found (priority contact)", "found_other": "found (not marketing/owner)",
    "not_found": "not found", "not_needed": "not needed", "skipped_no_website": "no website",
    "skipped_business_closed": "skipped (closed)",
}
FB_LABEL = {
    "checked_email_found": "email found", "checked_no_email": "page checked, no email shown",
    "no_page_found": "no page found", "needs_browser": "page found but contact details hidden behind login",
    "skipped_business_closed": "skipped (closed)",
}
GES_LABEL = {"found": "found", "not_found": "nothing found", "not_needed": "not needed",
             "skipped_business_closed": "skipped (closed)"}
SOURCE_RANK = {"website": 0, "facebook": 1, "google": 2}
GENERIC_ORDER = ["info", "hello", "contact", "enquiries", "enquiry", "inquiries", "office", "admin", "sales",
                 "marketing", "bookings"]
DEFAULT_WIDTHS = {
    "BUSINESS NAME": 28, "BUSINESS ADDRESS": 34, "CLOSEST LOCATION": 18, "CITY/TOWN": 16, "CONTACT NUMBER": 17,
    "CONTACT NAME": 26, "BUSINESS E-MAIL ADDRESS": 30, "CONTACT E-MAIL ADDRESS": 30, "ACTIONS": 34,
    "ADVERTISING ELIGIBILITY": 14, "JUSTIFICATION": 50, "NOTES": 50, "CATEGORY": 20, "WEBSITE": 30,
    "SOURCE LINKS": 60, "AUDIT NOTES": 50, "ROW ID": 8, "REASON": 40,
}


def research_path(run_dir: Path, row_id: str) -> Path:
    return run_dir / "research" / f"{row_id}.json"


def load_research(run_dir, row, cfg):
    """Return (research_or_None, errors). Missing file -> (None, ['not researched'])."""
    p = research_path(run_dir, row["row_id"])
    if not p.exists():
        return None, ["Not researched yet."]
    try:
        d = read_json(p)
    except Exception as e:  # malformed JSON
        return None, [f"Research file is not valid JSON: {e}"]
    return d, validate(row, d, cfg)


def split_emails(d, extra_generic):
    contact_name = (d.get("contact") or {}).get("name") or ""
    business = d.get("business_name") or ""
    generic, named = [], []
    items = sorted(enumerate(d.get("emails") or []),
                   key=lambda ie: (SOURCE_RANK.get(ie[1].get("found_on"), 9), ie[0]))
    for _, e in items:
        addr = em.clean(e.get("address", ""))
        if not addr:
            continue
        kind = em.classify(addr, contact_name, e.get("kind"), extra_generic, business)
        (generic if kind == "generic" else named).append(addr)

    def generic_rank(a):
        local = a.split("@")[0]
        return next((i for i, g in enumerate(GENERIC_ORDER) if local.startswith(g)), len(GENERIC_ORDER))

    generic.sort(key=generic_rank)  # sorts addresses inside one cell only - rows are never sorted
    if contact_name:
        first = em._name_tokens(contact_name)[:1]
        named.sort(key=lambda a: 0 if first and first[0] in a.split("@")[0] else 1)
    return list(dict.fromkeys(generic)), list(dict.fromkeys(named))


def source_links(d, label, extra=()):
    """Every verification URL, de-duplicated, one per line, optionally labelled with what it proves."""
    links = {}

    def add(url, what):
        if isinstance(url, str) and url.startswith("http"):
            links.setdefault(url.strip(), [])
            if what not in links[url.strip()]:
                links[url.strip()].append(what)

    c = d.get("contact") or {}
    if c.get("name"):
        add(c.get("source_url"), "Contact")
    for e in d.get("emails") or []:
        add(e.get("source_url"), f"Email {em.clean(e.get('address', ''))}")
    fb = d.get("facebook") or {}
    add(fb.get("page_url"), "Facebook")
    for u in (d.get("eligibility") or {}).get("evidence_urls") or []:
        add(u, "Eligibility")
    for u in extra or []:
        add(u, "Business details")
    if not label:
        return "\n".join(links)
    return "\n".join(f"{' + '.join(w)}: {u}" for u, w in links.items())


def audit_trail(d):
    cs = d.get("contact_search") or {}
    parts = [f"{name} - {STEP_LABEL.get((cs.get(k) or {}).get('outcome'), '?')}"
             for k, name in (("website", "Website"), ("google", "Google"), ("linkedin", "LinkedIn"))]
    fb = d.get("facebook") or {}
    via = fb.get("checked_via")
    fb_txt = FB_LABEL.get(fb.get("status"), "?") + (f" (checked via {via})" if via in ("browser", "fetch") else "")
    ges = GES_LABEL.get((d.get("google_email_search") or {}).get("outcome"), "?")
    out = f"Contact search: {'; '.join(parts)}. Facebook: {fb_txt}. Google email search: {ges}."
    extra = text(d.get("audit_notes"))
    return f"{out} {extra}".strip()


def notes_cell(d):
    c = d.get("contact") or {}
    prefix = ""
    if c.get("name") and c.get("source") == "google":
        prefix = "Contact found via Google search."
    elif c.get("name") and c.get("source") == "linkedin":
        prefix = "Contact found via LinkedIn (Google search result)."
    return f"{prefix} {text(d.get('notes'))}".strip()


def actions_cell(d, generic, named):
    acts = []
    status = (d.get("eligibility") or {}).get("status")
    fb = d.get("facebook") or {}
    if status == "Delete":
        acts.append("Delete - see JUSTIFICATION")
    else:
        if fb.get("status") == "needs_browser":
            acts.append("Check Facebook page for an email (link in SOURCE LINKS)")
        if not generic and not named:
            acts.append("No email found - phone or use the website contact form")
        if status == "Review":
            acts.append("Review eligibility - see JUSTIFICATION")
    extra = text(d.get("action_notes"))
    if extra:
        acts.append(extra)
    if not acts and status == "Suitable":
        acts.append("Ready to email")
    return "; ".join(acts)


def compose(row, d, errors, cfg):
    out_cfg = cfg.get("output", {})
    f = {
        "row_id": row["row_id"],
        "business_name": row["business_name"],
        "business_address": row["address"],
        "city": row.get("city", ""),
        "closest_location": row.get("closest_location") or (text((d or {}).get("closest_location")) if not errors else ""),
        "phone": row["phone"],
        "category": row["category"],
        "website": row["website"] or (text((d or {}).get("website_url")) if not errors else ""),
    }
    if errors:
        f.update({
            "eligibility": "Review",
            "actions": "Research incomplete - research this business manually",
            "audit_notes": "Automatic research did not pass the checks: " + " | ".join(errors[:4]),
        })
        return f
    generic, named = split_emails(d, cfg.get("emails", {}).get("extra_generic_prefixes", []))
    sep = out_cfg.get("email_separator", ", ")
    c = d.get("contact") or {}
    f.update({
        "contact_name": f"{c['name']} ({c['job_title']})" if c.get("name") else "",
        "business_emails": sep.join(generic),
        "contact_emails": sep.join(named),
        "eligibility": d["eligibility"]["status"],
        "justification": text(d["eligibility"].get("justification")),
        "notes": notes_cell(d),
        "audit_notes": audit_trail(d),
        "source_links": source_links(d, out_cfg.get("label_source_links", True), row.get("lookup_sources")),
        "actions": actions_cell(d, generic, named),
    })
    return f


def build_tabs(run_dir: Path, rows_doc: dict, cfg: dict, stats=None):
    """Return [(tab name, headers, rows), ...] exactly as they appear in the spreadsheet."""
    out_cfg = cfg.get("output", {})
    header_fields = out_cfg.get("header_fields", {})
    cols = {"with": out_cfg.get("columns_with_address", []), "without": out_cfg.get("columns_no_address", [])}
    tabs = {"with": [], "without": []}
    stats = stats if stats is not None else {}
    for k in ("rows", "Suitable", "Review", "Delete", "ready", "with_email", "named_email", "contact", "fb_manual",
              "incomplete"):
        stats.setdefault(k, 0)
    for row in rows_doc["rows"]:  # original file order - never sorted
        d, errors = load_research(run_dir, row, cfg)
        f = compose(row, d, errors, cfg)
        key = "with" if row["has_address"] else "without"
        tabs[key].append([f.get(header_fields.get(h, ""), "") for h in cols[key]])
        stats["rows"] += 1
        stats[f.get("eligibility", "Review")] = stats.get(f.get("eligibility", "Review"), 0) + 1
        if errors:
            stats["incomplete"] += 1
            continue
        stats["ready"] += f["actions"] == "Ready to email"
        stats["with_email"] += bool(f["business_emails"] or f["contact_emails"])
        stats["named_email"] += bool(f["contact_emails"])
        stats["contact"] += bool(f["contact_name"])
        stats["fb_manual"] += (d.get("facebook") or {}).get("status") == "needs_browser"
    drop_headers = ["ROW ID", "BUSINESS NAME", "BUSINESS ADDRESS", "CONTACT NUMBER", "WEBSITE", "CATEGORY", "REASON"]
    dropped = [[r["row_id"], r["business_name"], r["address"], r["phone"], r["website"], r["category"],
                r.get("drop_reason", "")] for r in rows_doc.get("dropped", [])]
    return [("With address", cols["with"], tabs["with"]), ("No address", cols["without"], tabs["without"]),
            ("Filtered out", drop_headers, dropped)]


def build(run_dir: Path, rows_doc: dict, cfg: dict):
    stats = {}
    sheets = build_tabs(run_dir, rows_doc, cfg, stats)
    out_cfg = cfg.get("output", {})
    out = output_dir()
    out.mkdir(parents=True, exist_ok=True)
    name = run_dir.name
    xlsx_path = out / f"{name}.xlsx"
    try:
        write_xlsx(xlsx_path, sheets, {**DEFAULT_WIDTHS, **out_cfg.get("column_widths", {})})
    except PermissionError:
        xlsx_path = out / f"{name} (new).xlsx"  # the old file is open in Excel
        write_xlsx(xlsx_path, sheets, {**DEFAULT_WIDTHS, **out_cfg.get("column_widths", {})})
    csv_paths = []
    for tab_name, headers, rows in sheets[:2]:
        p = out / f"{name} - {tab_name}.csv"
        try:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(headers)
                w.writerows(rows)
            csv_paths.append(p)
        except PermissionError:
            pass
    stats["with_address_rows"], stats["no_address_rows"], stats["dropped"] = (
        len(sheets[0][2]), len(sheets[1][2]), len(sheets[2][2]))
    return xlsx_path, csv_paths, stats
