"""Step 1: read the raw scraper export, map its columns, filter, de-duplicate.

Rows keep their original order from the file. Nothing here (or anywhere else) sorts rows.
Every dropped row is kept with the reason it was dropped, so the filtering can be audited.
"""
import csv
import io
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import emails as em
from common import die, norm, text

# Header aliases for common Google Maps scrapers (gosom, Outscraper, Apify, G Maps Extractor, ...).
# First match wins, so more specific names come first.
FIELD_ALIASES = {
    "business_name": ["business name", "name", "title", "company name", "company", "place name", "business"],
    "address": ["business address", "full address", "full_address", "address", "formatted address",
                "street address", "complete address", "complete_address"],
    "city": ["city/town", "city", "town", "locality", "municipality", "area", "town/city", "location town"],
    "phone": ["contact number", "phone", "phone number", "phone_number", "telephone", "tel",
              "international phone", "international phone number", "phone 1", "phoneunformatted"],
    "website": ["website", "web site", "site", "website url", "domain", "homepage"],
    "category": ["category", "main category", "categoryname", "category name", "type", "business type",
                 "primary category", "categories", "subtypes"],
    "status": ["business status", "business_status", "status", "closed status", "open status"],
    "permanently_closed": ["permanently closed", "permanentlyclosed", "is permanently closed", "closed permanently"],
    "temporarily_closed": ["temporarily closed", "temporarilyclosed", "is temporarily closed", "closed temporarily"],
    "rating": ["rating", "review rating", "review_rating", "totalscore", "total score", "stars", "average rating"],
    "reviews": ["reviews", "review count", "review_count", "reviewscount", "reviews count", "number of reviews",
                "user ratings total", "total reviews"],
    "place_id": ["place id", "place_id", "placeid", "google place id", "google id", "cid", "data id", "data_id", "fid"],
    "maps_url": ["google maps url", "maps url", "google maps link", "place url", "location link", "location_link",
                 "link", "url"],
    "emails": ["emails", "email", "e-mail", "email address", "e-mail address", "emails found", "email 1"],
    "facebook": ["facebook", "facebook url", "facebook link", "facebook page"],
    "query": ["query", "search query", "keyword", "search term", "searchstring", "search string"],
}
FIELD_LABELS = {
    "business_name": "Business name", "address": "Address", "city": "City/town", "phone": "Phone",
    "website": "Website", "category": "Category", "status": "Open/closed status",
    "permanently_closed": "Permanently closed flag", "temporarily_closed": "Temporarily closed flag",
    "rating": "Rating", "reviews": "Review count", "place_id": "Place ID", "maps_url": "Google Maps link",
    "emails": "Emails", "facebook": "Facebook", "query": "Search query",
}
NOT_A_WEBSITE = ("facebook.com", "fb.com", "fb.me", "instagram.com", "linkedin.com", "twitter.com", "x.com",
                 "tiktok.com", "youtube.com", "linktr.ee", "wa.me", "yelp.com", "yell.com", "checkatrade.com",
                 "bark.com", "nextdoor.com", "thumbtack.com", "angi.com", "homeadvisor.com", "houzz.com",
                 "houzz.co.uk", "trustatrader.com", "mybuilder.com", "ratedpeople.com")
PLUS_CODE_RE = re.compile(r"\b[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3}\b", re.I)
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|_hs|ref$)", re.I)


# ---------------------------------------------------------------- reading
def read_table(path: Path):
    """Return (headers, rows) where rows is a list of (spreadsheet_row_number, [values])."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        from xlsx import read_xlsx
        grid = read_xlsx(path)
    elif suffix in (".csv", ".tsv", ".txt"):
        raw = path.read_bytes()
        content = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                content = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        first_line = content.split("\n", 1)[0]
        if suffix == ".txt" and "\t" not in first_line:
            # a plain list: one business name per line (names may contain commas)
            grid = [[ln.strip()] for ln in content.splitlines()]
        else:
            delim = max([",", ";", "\t"], key=first_line.count)
            grid = list(csv.reader(io.StringIO(content), delimiter=delim))
    else:
        die(f"Unsupported file type '{suffix}'. Use .csv, .xlsx or .txt (in Google Sheets: File > Download).")
    # first non-empty row is the header
    start = next((i for i, r in enumerate(grid) if any(text(c) for c in r)), None)
    if start is None:
        die(f"{path.name} is empty.")
    headers = [text(h) or f"Column {i + 1}" for i, h in enumerate(grid[start])]
    first_data = start + 1
    filled_cols = [h for h, c in zip(headers, grid[start]) if text(c)]
    if len(filled_cols) == 1 and not is_known_header(filled_cols[0]):
        # A single column without a recognised header is a plain list of names: keep its first line as data.
        headers = ["Business name"] + headers[1:]
        first_data = start
    rows = []
    for i, r in enumerate(grid[first_data:], start=first_data + 1):
        if any(text(c) for c in r):
            vals = [text(c) for c in r] + [""] * max(0, len(headers) - len(r))
            rows.append((i, vals[:len(headers)]))
    return headers, rows


def is_known_header(h) -> bool:
    n = norm(h)
    return any(n == norm(a) for aliases in FIELD_ALIASES.values() for a in aliases)


def detect_mapping(headers, rows, overrides):
    normmap = {}
    for h in headers:
        normmap.setdefault(norm(h), h)
    mapping, used = {}, set()
    for field, header in (overrides or {}).items():
        if field.startswith("_") or not header:
            continue
        if header not in headers:
            die(f'config.json input_columns.{field} = "{header}", but the file has no such column. '
                f"Columns in the file: {', '.join(headers)}")
        mapping[field] = header
        used.add(header)
    def filled(h):
        idx = headers.index(h)
        return any(r[idx] for _, r in rows[:200])

    for field, aliases in FIELD_ALIASES.items():
        if field in mapping:
            continue
        cands = []
        for a in aliases:
            h = normmap.get(norm(a))
            if h and h not in used and h not in cands:
                cands.append(h)
        if cands:  # first alias that actually has data wins; fall back to the first match
            h = next((c for c in cands if filled(c)), cands[0])
            mapping[field] = h
            used.add(h)
    # A bare "url"/"link" column might be the website rather than a Google Maps link.
    if "maps_url" in mapping and norm(mapping["maps_url"]) in ("url", "link"):
        idx = headers.index(mapping["maps_url"])
        sample = [r[idx] for _, r in rows[:50] if r[idx]]
        looks_maps = sum("google." in v or "goo.gl" in v for v in sample) >= max(1, len(sample) // 2)
        if not looks_maps:
            h = mapping.pop("maps_url")
            if "website" not in mapping:
                mapping["website"] = h
    return mapping


# ---------------------------------------------------------------- cleaning helpers
def clean_website(v: str) -> str:
    v = text(v)
    if not v:
        return ""
    if "google." in v and "/url?" in v:
        q = dict(parse_qsl(urlsplit(v).query)).get("q")
        if q:
            v = q
    try:
        parts = urlsplit(v if "://" in v else "http://" + v)
        query = urlencode([(k, val) for k, val in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)])
        cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
        return cleaned if "://" in v else cleaned.split("://", 1)[1]
    except ValueError:
        return v


def website_domain(v: str) -> str:
    v = text(v)
    if not v:
        return ""
    try:
        host = urlsplit(v if "://" in v else "http://" + v).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def phone_key(v: str) -> str:
    digits = re.sub(r"\D", "", text(v))
    return digits[-10:] if len(digits) >= 7 else ""


def clean_category(v: str, header: str) -> str:
    v = text(v)
    if v.startswith("["):
        v = v.strip("[]").split(",")[0]
    elif norm(header) in ("categories", "subtypes"):
        v = v.split(",")[0]
    return v.strip().strip("'\"").strip()


def to_number(v):
    m = re.search(r"\d[\d,]*\.?\d*", text(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def truthy(v) -> bool:
    return norm(v) in ("true", "yes", "y", "1")


def has_street_address(addr: str) -> bool:
    """Service-area businesses show no street address on Google Maps (or just a town / plus code)."""
    s = PLUS_CODE_RE.sub("", text(addr)).strip(" ,")
    return len(s) >= 6 and bool(re.search(r"\d", s))


def guess_closest_location(city: str, addr: str, query: str) -> str:
    if city:
        return city
    s = PLUS_CODE_RE.sub("", text(addr)).strip(" ,")
    if s and not re.search(r"\d", s):
        return s.split(",")[0].strip()
    m = re.search(r"\b(?:in|near)\s+(.+)$", text(query), re.I)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------- records
def build_record(line_no, vals, headers, mapping):
    get = lambda f: text(vals[headers.index(mapping[f])]) if f in mapping else ""
    address = get("address")
    st = norm(get("status"))
    closed = ""
    if truthy(get("permanently_closed")) or "permanentlyclosed" in st or "closedpermanently" in st:
        closed = "permanent"
    elif truthy(get("temporarily_closed")) or "temporarilyclosed" in st or "closedtemporarily" in st:
        closed = "temporary"
    rec = {
        "row_id": "",  # assigned after reading, from the original order
        "source_row": line_no,
        "business_name": get("business_name"),
        "address": address,
        "has_address": has_street_address(address),
        "city": get("city"),
        "closest_location": "",
        "phone": get("phone"),
        "website": clean_website(get("website")),
        "category": clean_category(get("category"), mapping.get("category", "")),
        "rating": to_number(get("rating")),
        "reviews": to_number(get("reviews")),
        "place_id": get("place_id"),
        "maps_url": get("maps_url"),
        "facebook": get("facebook"),
        "scraper_emails": em.extract(get("emails")),
        "query": get("query"),
        "closed": closed,
        "raw": {h: (v[:300] + "...") if len(v) > 300 else v for h, v in zip(headers, vals) if v},
    }
    # A Facebook page or directory listing in the website column is not a website.
    dom = website_domain(rec["website"])
    if dom and any(dom == h or dom.endswith("." + h) for h in NOT_A_WEBSITE):
        if "facebook" in dom or dom in ("fb.com", "fb.me"):
            rec["facebook"] = rec["facebook"] or rec["website"]
        else:
            rec["listing_url"] = rec["website"]
        rec["website"] = ""
    if not rec["has_address"]:
        rec["closest_location"] = guess_closest_location(rec["city"], address, rec["query"])
    # Only a name (no website, phone or address)? The lookup step finds the rest before research.
    rec["needs_lookup"] = bool(rec["business_name"]) and not (rec["website"] or rec["phone"] or address)
    rec["input_name"] = rec["business_name"]
    return rec


DEDUPE_LABELS = {"place_id": "Google place ID", "phone": "phone number", "website_domain": "website",
                 "name": "business name"}


def dedupe_key(rec, kind, ignore_domains):
    if kind == "place_id":
        return rec["place_id"]
    if kind == "phone":
        return phone_key(rec["phone"])
    if kind == "website_domain":
        d = website_domain(rec["website"])
        if not d or any(d == x or d.endswith("." + x) for x in ignore_domains):
            return ""
        return d
    if kind == "name":
        return norm(rec["business_name"])
    return ""


def apply_filters(records, f):
    kept, dropped, seen = [], [], {}
    lower = lambda xs: [s.lower() for s in (xs or []) if s]
    excl_cat = lower(f.get("exclude_if_category_contains"))
    keep_cat = lower(f.get("keep_only_if_category_contains"))
    excl_name = lower(f.get("exclude_if_name_contains"))
    min_reviews, min_rating = f.get("min_reviews"), f.get("min_rating")
    dedupe_on = f.get("dedupe_on") or []
    ignore = lower(f.get("dedupe_ignore_domains"))
    for r in records:
        reason = None
        cat, name = r["category"].lower(), r["business_name"].lower()
        if f.get("drop_if_no_name", True) and not r["business_name"]:
            reason = "No business name"
        elif f.get("drop_permanently_closed", True) and r["closed"] == "permanent":
            reason = "Permanently closed"
        elif f.get("drop_temporarily_closed") and r["closed"] == "temporary":
            reason = "Temporarily closed"
        elif excl_cat and any(s in cat for s in excl_cat):
            reason = f"Excluded category ({r['category']})"
        elif keep_cat and not any(s in cat for s in keep_cat):
            reason = f"Category not in keep list ({r['category'] or 'no category'})"
        elif excl_name and any(s in name for s in excl_name):
            reason = "Name matches exclude list"
        elif min_reviews is not None and r["reviews"] is not None and r["reviews"] < min_reviews:
            reason = f"Fewer than {min_reviews} reviews"
        elif min_rating is not None and r["rating"] is not None and r["rating"] < min_rating:
            reason = f"Rating below {min_rating}"
        elif f.get("drop_if_no_website_and_no_phone") and not r["website"] and not r["phone"]:
            reason = "No website and no phone"
        kinds = list(dedupe_on) + (["name"] if r.get("needs_lookup") and "name" not in dedupe_on else [])
        if not reason:
            for kind in kinds:
                k = dedupe_key(r, kind, ignore)
                if k and (kind, k) in seen:
                    reason = f"Duplicate of {seen[(kind, k)]} (same {DEDUPE_LABELS.get(kind, kind)})"
                    break
        if reason:
            r["drop_reason"] = reason
            dropped.append(r)
            continue
        for kind in kinds:
            k = dedupe_key(r, kind, ignore)
            if k:
                seen.setdefault((kind, k), r["row_id"])
        r.pop("raw", None)  # only dropped rows need the raw data (for the Filtered out tab)
        kept.append(r)
    return kept, dropped


def import_file(path: Path, cfg: dict):
    headers, rows = read_table(path)
    mapping = detect_mapping(headers, rows, cfg.get("input_columns"))
    if "business_name" not in mapping:
        die("Couldn't find the business name column. Columns in the file: " + ", ".join(headers) +
            '. Set it in config.json, e.g. "input_columns": {"business_name": "<header>"}.')
    records = []
    for n, (line_no, vals) in enumerate(rows, start=1):
        rec = build_record(line_no, vals, headers, mapping)
        rec["row_id"] = f"R{n:04d}"
        records.append(rec)
    kept, dropped = apply_filters(records, cfg.get("filters", {}))
    return headers, mapping, records, kept, dropped
