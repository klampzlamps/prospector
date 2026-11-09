"""The rulebook. Every research file must pass validate() before it can reach the spreadsheet.

Each rule here is one the workflow depends on. Error messages are written for the research
agent: they say exactly what is wrong and how to fix it.
"""
import re

import emails as em
from common import norm, text

ELIGIBILITY = ("Suitable", "Review", "Delete")
TRADING = ("trading", "closed", "unclear")
STEPS = ("website", "google", "linkedin")
STEP_OUTCOMES = ("found_priority", "found_other", "not_found", "not_needed", "skipped_no_website",
                 "skipped_business_closed")
ROLE_TYPES = ("marketing", "owner", "senior", "other")
PRIORITY_ROLES = ("marketing", "owner")
EMAIL_FOUND_ON = ("website", "facebook", "google")
EMAIL_KINDS = ("generic", "named")
FB_STATUS = ("checked_email_found", "checked_no_email", "no_page_found", "needs_browser", "skipped_business_closed")
FB_VIA = ("browser", "fetch", "search_snippet", "none")
GES_OUTCOMES = ("found", "not_found", "not_needed", "skipped_business_closed")

URL_RE = re.compile(r"^https?://[^\s]+\.[^\s]+$", re.I)
URL_IN_TEXT = re.compile(r"(https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:com|co\.uk|org|net|io|uk|us|biz|info)/\S*)", re.I)
FB_URL_RE = re.compile(r"(facebook\.com|fb\.com|fb\.me)/", re.I)
ROLE_PHRASES = [  # longest first
    "head of marketing", "marketing director", "marketing manager", "marketing coordinator", "marketing lead",
    "managing director", "general manager", "chief executive", "co-founder", "co-owner", "founder", "owner",
    "proprietor", "director", "ceo", "president", "principal", "partner", "manager",
]
OWNER_DESCRIPTIONS = re.compile(r"owner[- ](?:operated|run|managed|led)|family[- ]owned|independently owned|locally owned", re.I)
LIMITS = {"notes": (20, 700), "audit_notes": (0, 500), "action_notes": (0, 300)}


def _is_url(v):
    return isinstance(v, str) and bool(URL_RE.match(v.strip()))


def _str(v):
    return isinstance(v, str) and v.strip() != ""


def _name_variants(person: str):
    """Full name (any case) plus first/last name as written (capitalised), to avoid matching ordinary words."""
    person = re.sub(r"\(.*?\)", " ", person or "").strip()
    toks = [t for t in re.findall(r"[A-Za-z][A-Za-z'\-]+", person)
            if t.lower() not in {"mr", "mrs", "ms", "miss", "dr", "prof", "sir"}]
    out = []
    if len(toks) >= 2:
        out.append((re.compile(r"\b" + r"\s+".join(map(re.escape, toks)) + r"\b", re.I), " ".join(toks)))
    for t in (toks[:1] + toks[-1:] if len(toks) > 1 else toks):
        if len(t) >= 3:
            out.append((re.compile(r"\b" + re.escape(t[0].upper() + t[1:]) + r"\b"), t))
    return out


def _scrub(s: str, business_name: str):
    """Remove the business name, URLs and emails before name checks (a surname inside 'Smith Realty' is fine)."""
    s = s or ""
    if business_name:
        s = re.sub(re.escape(business_name), " ", s, flags=re.I)
    s = em.EMAIL_RE.sub(" ", s)
    s = URL_IN_TEXT.sub(" ", s)
    return s


def validate(row, d, cfg=None):
    E = []
    err = E.append
    if not isinstance(d, dict):
        return ["The file must contain one JSON object (use the template from the `row` command)."]

    # ---------- identity: stops research being written to the wrong business
    if d.get("row_id") != row["row_id"]:
        err(f'row_id must be "{row["row_id"]}".')
    if norm(d.get("business_name")) != norm(row["business_name"]):
        err(f'business_name must be exactly "{row["business_name"]}" (copy it from the row). '
            "This guards against writing research for the wrong business.")

    trading = d.get("trading_status")
    if trading not in TRADING:
        err(f"trading_status must be one of {list(TRADING)}.")
    closed = trading == "closed"

    website_url = d.get("website_url")
    if website_url not in (None, "") and not _is_url(website_url):
        err("website_url must be a full URL starting with http(s):// or null if the business has no website.")
    has_site = _str(website_url)

    if not closed and not row.get("has_address") and not row.get("closest_location") \
            and not _str(d.get("closest_location")):
        err("This is a service-area business (no street address) and the scraper gave no town. Set closest_location "
            "to the town/city it is based in or nearest to (from its website, Google listing or Facebook).")

    people = d.get("people_seen_on_website")
    if not isinstance(people, list) or not all(isinstance(p, str) for p in people):
        err("people_seen_on_website must be a list of names (strings) - every person named on the company "
            "website, or [] if none.")
        people = []

    # ---------- contact search order: website -> Google -> LinkedIn
    cs = d.get("contact_search")
    outcomes = {}
    if not isinstance(cs, dict):
        err("contact_search must be an object with website, google and linkedin steps.")
        cs = {}
    for s in STEPS:
        step = cs.get(s)
        if not isinstance(step, dict):
            err(f"contact_search.{s} is missing.")
            continue
        o = step.get("outcome")
        if o not in STEP_OUTCOMES:
            err(f"contact_search.{s}.outcome must be one of {list(STEP_OUTCOMES)}.")
            continue
        outcomes[s] = o
        urls = step.get("urls", [])
        if not isinstance(urls, list) or not all(_is_url(u) for u in urls):
            err(f"contact_search.{s}.urls must be a list of full URLs.")
            urls = []
        if s != "website":
            queries = step.get("queries", [])
            if not isinstance(queries, list):
                err(f"contact_search.{s}.queries must be a list of the searches you ran.")
                queries = []
            if o in ("found_priority", "found_other", "not_found") and not queries:
                err(f"contact_search.{s}.queries is empty - list the exact searches you ran for this step.")
            if s == "linkedin" and o in ("found_priority", "found_other", "not_found") and queries \
                    and not any("linkedin" in str(q).lower() for q in queries):
                err("contact_search.linkedin.queries must include a LinkedIn search, e.g. "
                    'site:linkedin.com/in "<Business Name>".')
        if o in ("found_priority", "found_other") and not urls:
            err(f"contact_search.{s}.urls must include the page where you found the contact.")
        if s == "website" and o == "not_found" and not urls:
            err("contact_search.website.urls must list the website pages you checked.")
        if o == "skipped_no_website" and s != "website":
            err(f"contact_search.{s}.outcome cannot be skipped_no_website (only the website step can).")

    if len(outcomes) == 3:
        vals = [outcomes[s] for s in STEPS]
        if "skipped_business_closed" in vals:
            if not closed:
                err("A step is skipped_business_closed but trading_status is not 'closed'.")
            elif any(v != "skipped_business_closed" for v in vals):
                err("If the business is closed, set all three contact_search steps to skipped_business_closed.")
        else:
            if outcomes["website"] == "skipped_no_website" and has_site:
                err("contact_search.website is skipped_no_website but website_url is set. Check the website.")
            if outcomes["website"] != "skipped_no_website" and not has_site:
                err("website_url is null, so contact_search.website.outcome must be skipped_no_website "
                    "(or set website_url if you found the website).")
            fp = next((i for i, v in enumerate(vals) if v == "found_priority"), None)
            if fp is not None:
                for j in range(fp):
                    if vals[j] not in ("not_found", "found_other", "skipped_no_website"):
                        err(f"contact_search.{STEPS[j]} must be done before {STEPS[fp]} "
                            f"(order: website, then Google, then LinkedIn).")
                for j in range(fp + 1, 3):
                    if vals[j] != "not_needed":
                        err(f"A priority contact was already found via {STEPS[fp]}, so contact_search.{STEPS[j]} "
                            f"must be not_needed (stop searching once a priority contact is found).")
            else:
                for j, v in enumerate(vals):
                    if v == "not_needed":
                        err(f"No priority (marketing/owner) contact was found before {STEPS[j]}, so that step "
                            f"must actually be done - its outcome cannot be not_needed.")

    # ---------- contact
    c = d.get("contact")
    if not isinstance(c, dict):
        err("contact must be an object (name, job_title, role_type, source, source_url) - use nulls if none found.")
        c = {}
    found_steps = [s for s, o in outcomes.items() if o in ("found_priority", "found_other")]
    priority_step = next((s for s, o in outcomes.items() if o == "found_priority"), None)
    if found_steps:
        if not _str(c.get("name")):
            err(f"contact_search says a contact was found ({', '.join(found_steps)}) but contact.name is empty.")
        else:
            nm = c["name"]
            if "@" in nm or "http" in nm.lower() or norm(nm) == norm(row["business_name"]):
                err("contact.name must be a person's name (not an email, URL or the business name).")
            if "(" in nm:
                err("contact.name must be the name only - put the role in contact.job_title (the sheet adds it).")
        if not _str(c.get("job_title")):
            err("contact.job_title is required (e.g. Owner, Marketing Manager).")
        if c.get("role_type") not in ROLE_TYPES:
            err(f"contact.role_type must be one of {list(ROLE_TYPES)}.")
        if c.get("source") not in found_steps:
            err(f"contact.source must be the step where you found them: one of {found_steps}.")
        elif priority_step and c.get("source") != priority_step:
            err(f"A priority contact was found via {priority_step}, so contact.source must be {priority_step}.")
        if not _is_url(c.get("source_url")):
            err("contact.source_url must be the full URL of the page that shows this person and their role.")
        src = c.get("source")
        if src in outcomes and c.get("role_type") in ROLE_TYPES:
            is_pri = c["role_type"] in PRIORITY_ROLES
            if is_pri and outcomes[src] != "found_priority":
                err(f"contact.role_type is {c['role_type']} (a priority role), so contact_search.{src}.outcome "
                    f"must be found_priority.")
            if not is_pri and outcomes[src] == "found_priority":
                err(f"contact_search.{src} is found_priority but contact.role_type is {c['role_type']}. "
                    f"Priority means marketing or owner; use found_other for anyone else.")
    elif _str(c.get("name")):
        err("contact.name is set but no contact_search step says found_priority/found_other. Fix the step outcomes.")

    # ---------- emails
    emails = d.get("emails")
    if not isinstance(emails, list):
        err("emails must be a list (use [] if none found).")
        emails = []
    seen, by_source = set(), {k: 0 for k in EMAIL_FOUND_ON}
    for i, e in enumerate(emails):
        if not isinstance(e, dict):
            err(f"emails[{i}] must be an object with address, kind, found_on, source_url.")
            continue
        addr = em.clean(e.get("address", ""))
        label = f"emails[{i}] ({addr or 'blank'})"
        if not em.is_valid(addr):
            err(f"{label}: not a valid email address.")
        else:
            jr = em.junk_reason(addr)
            if jr:
                err(f"{label}: {jr} - remove it.")
        if addr in seen:
            err(f"{label}: listed twice - keep one entry.")
        seen.add(addr)
        if e.get("kind") not in EMAIL_KINDS:
            err(f'{label}: kind must be "generic" (info@, sales@...) or "named" (a person, e.g. john@).')
        if e.get("found_on") not in EMAIL_FOUND_ON:
            err(f"{label}: found_on must be one of {list(EMAIL_FOUND_ON)}.")
        else:
            by_source[e["found_on"]] += 1
        if not _is_url(e.get("source_url")):
            err(f"{label}: source_url must be the full URL where you saw this address.")

    # ---------- Facebook: always checked, even if the website already had an email
    fb = d.get("facebook")
    if not isinstance(fb, dict):
        err("facebook must be an object (page_url, status, checked_via, queries). Facebook is ALWAYS checked.")
        fb = {}
    st, via = fb.get("status"), fb.get("checked_via")
    if st not in FB_STATUS:
        err(f"facebook.status must be one of {list(FB_STATUS)}. Facebook must be checked for every business, "
            "even if the website already shows an email.")
    if via not in FB_VIA:
        err(f"facebook.checked_via must be one of {list(FB_VIA)}.")
    if st == "skipped_business_closed" and not closed:
        err("facebook.status is skipped_business_closed but trading_status is not 'closed'.")
    if st in ("checked_email_found", "checked_no_email", "needs_browser"):
        if not (_is_url(fb.get("page_url")) and FB_URL_RE.search(fb.get("page_url", ""))):
            err("facebook.page_url must be the full facebook.com URL of the business's page.")
    if st == "no_page_found":
        q = fb.get("queries")
        if via != "browser" and not (isinstance(q, list) and q):
            err("facebook.status is no_page_found - list the searches you ran in facebook.queries.")
    if st == "checked_email_found" and by_source["facebook"] == 0:
        err('facebook.status is checked_email_found but no email has found_on "facebook".')
    if by_source["facebook"] and st != "checked_email_found":
        err('An email has found_on "facebook", so facebook.status must be checked_email_found.')
    if st == "checked_no_email" and via not in ("browser", "fetch"):
        err("checked_no_email is only allowed if you actually saw the page's contact details (checked_via browser "
            "or fetch). If you only saw search results, use needs_browser.")

    # ---------- Google email search: required when website + Facebook gave no email
    ges = d.get("google_email_search")
    if not isinstance(ges, dict):
        err("google_email_search must be an object (outcome, queries).")
        ges = {}
    go = ges.get("outcome")
    if go not in GES_OUTCOMES:
        err(f"google_email_search.outcome must be one of {list(GES_OUTCOMES)}.")
    if go == "skipped_business_closed" and not closed:
        err("google_email_search is skipped_business_closed but trading_status is not 'closed'.")
    if not closed and by_source["website"] + by_source["facebook"] == 0 and go not in ("found", "not_found"):
        err("No email came from the website or Facebook, so you must search Google for one: set "
            "google_email_search.outcome to found or not_found and list the queries.")
    if go in ("found", "not_found") and not (isinstance(ges.get("queries"), list) and ges.get("queries")):
        err("google_email_search.queries must list the searches you ran.")
    if go == "found" and by_source["google"] == 0:
        err('google_email_search.outcome is found but no email has found_on "google".')
    if by_source["google"] and go != "found":
        err('An email has found_on "google", so google_email_search.outcome must be found.')

    # ---------- eligibility
    el = d.get("eligibility")
    if not isinstance(el, dict):
        err("eligibility must be an object (status, justification, evidence_urls).")
        el = {}
    status = el.get("status")
    if status not in ELIGIBILITY:
        fix = next((x for x in ELIGIBILITY if norm(x) == norm(status)), None)
        err(f'eligibility.status must be exactly "Suitable", "Review" or "Delete"' +
            (f' (write "{fix}", capitalised).' if fix else "."))
    j = el.get("justification")
    if not _str(j) or len(j.strip()) < 30:
        err("eligibility.justification must explain the status with specific evidence (at least one full sentence).")
    elif len(j) > 700:
        err("eligibility.justification is too long - keep it under 700 characters.")
    ev = el.get("evidence_urls")
    if not isinstance(ev, list) or not ev or not all(_is_url(u) for u in ev):
        err("eligibility.evidence_urls must list at least one full URL that supports the status.")
    if closed and status != "Delete":
        err('trading_status is closed, so eligibility.status must be "Delete".')
    if trading == "unclear" and status == "Suitable":
        err('trading_status is unclear, so eligibility.status cannot be "Suitable" - use "Review" (or "Delete").')

    # ---------- notes
    free = {"notes": d.get("notes"), "audit_notes": d.get("audit_notes"), "action_notes": d.get("action_notes"),
            "eligibility.justification": j}
    for key, (lo, hi) in LIMITS.items():
        v = free[key]
        if v is None:
            free[key] = ""
            v = ""
        if not isinstance(v, str):
            err(f"{key} must be text.")
            continue
        if key == "notes" and not closed and len(v.strip()) < lo:
            err("notes (research notes) is empty - add 1-3 sentences of useful findings about the business.")
        if len(v) > hi:
            err(f"{key} is too long ({len(v)} chars) - keep it under {hi}.")
    for key, v in free.items():
        if not isinstance(v, str) or not v:
            continue
        if URL_IN_TEXT.search(v):
            err(f"{key} contains a URL. URLs never go in notes - put them in the url/source_url/evidence_urls "
                "fields (they appear in the SOURCE LINKS column).")
        if em.EMAIL_RE.search(v):
            err(f"{key} contains an email address. Emails go only in the emails list.")

    # Website-found contacts must NEVER be mentioned in any notes field.
    website_people = list(people)
    if c.get("source") == "website" and _str(c.get("name")):
        website_people.append(c["name"])
    for key, v in free.items():
        if not isinstance(v, str) or not v:
            continue
        scrubbed = _scrub(v, row["business_name"])
        for person in dict.fromkeys(website_people):
            for rx, shown in _name_variants(person):
                if rx.search(scrubbed):
                    err(f"{key} mentions '{shown}' ({person}), who appears on the company website. People found "
                        f"on the company website must never be mentioned in notes, justification or audit notes. "
                        f"Remove it (their name already goes in the CONTACT NAME column).")
                    break
    if c.get("source") == "website" and _str(c.get("job_title")):
        title = c["job_title"].lower()
        phrase = next((p for p in ROLE_PHRASES if p in title), None)
        if phrase:
            rx = re.compile(r"\b" + re.escape(phrase) + r"\b", re.I)
            for key, v in free.items():
                if not isinstance(v, str) or not v:
                    continue
                cleaned = OWNER_DESCRIPTIONS.sub(" ", _scrub(v, row["business_name"]))
                if rx.search(cleaned):
                    err(f"{key} refers to the '{phrase}'. The contact ({c['job_title']}) was found on the company "
                        f"website, and website contacts must not be mentioned in notes at all. Remove that part.")
    return E
