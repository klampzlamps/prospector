"""Email extraction, junk filtering and generic-vs-named classification.

Classification is deterministic where the answer is obvious (info@, sales@, the contact's own name)
and only falls back to the researcher's label for ambiguous addresses.
"""
import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
EMAIL_FULL_RE = re.compile(r"^[a-z0-9._%+'-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,24}$")

# Role / shared mailbox local parts -> BUSINESS E-MAIL ADDRESS column.
GENERIC_LOCAL = {
    "info", "information", "contact", "contacts", "contactus", "hello", "hi", "hey", "enquiries", "enquiry",
    "enquire", "inquiries", "inquiry", "sales", "admin", "administrator", "administration", "office",
    "support", "help", "helpdesk", "team", "mail", "email", "post", "bookings", "booking", "book",
    "appointments", "appointment", "reservations", "reception", "frontdesk", "accounts", "account",
    "accounting", "billing", "invoices", "invoice", "finance", "payments", "marketing", "hr", "jobs",
    "careers", "recruitment", "service", "services", "customerservice", "customerservices", "customercare",
    "care", "orders", "order", "shop", "store", "studio", "general", "webmaster", "web", "website", "online",
    "events", "press", "media", "pr", "feedback", "newsletter", "news", "staff", "operations", "ops",
    "quotes", "quote", "estimates", "estimate", "projects", "dispatch", "clinic", "practice", "surgery",
    "salon", "spa", "gym", "hire", "rentals", "lettings", "leasing", "property", "properties", "legal",
    "privacy", "compliance", "management", "manager", "owner", "director", "partners", "workshop",
    "garage", "parts", "repairs", "info1", "office1", "mailbox", "inbox", "uk", "us", "usa", "team1",
}
# Starts-with checks catch things like "infoleeds@", "enquiries.uk@", "salesteam@".
GENERIC_PREFIXES = (
    "info", "enquir", "inquir", "contact", "hello", "sales", "admin", "office", "booking", "reception",
    "support", "accounts", "customerservice", "customercare", "webmaster", "noreply", "no-reply",
)

JUNK_DOMAINS = {
    "example.com", "example.org", "example.net", "domain.com", "yourdomain.com", "mydomain.com",
    "email.com", "sentry.io", "wixpress.com", "sentry.wixpress.com", "sentry-next.wixpress.com",
    "mysite.com", "yoursite.com", "website.com", "yourwebsite.com", "test.com", "company.com",
    "yourcompany.com", "address.com", "sample.com", "placeholder.com",
}
JUNK_LOCAL = {
    "user", "username", "name", "yourname", "your.name", "youremail", "your.email", "firstname",
    "first.last", "firstname.lastname", "john.doe", "jane.doe", "johndoe", "janedoe", "example", "test",
    "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster",
}
FILE_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "css", "js", "ico", "bmp", "tif", "tiff", "mp4",
             "pdf", "woff", "woff2", "ttf", "avif"}


def clean(addr: str) -> str:
    a = (addr or "").strip().strip(".,;:()[]<>\"'").lower()
    if a.startswith("mailto:"):
        a = a[7:]
    a = a.split("?")[0]
    # JSON-escaped HTML sometimes glues "u003e" (">") onto the front of an address.
    for junk in ("u003e", "u003c", "x3e", "%20", "20"):
        if a.startswith(junk) and EMAIL_FULL_RE.match(a[len(junk):] or ""):
            a = a[len(junk):]
            break
    return a


def is_valid(addr: str) -> bool:
    return bool(EMAIL_FULL_RE.match(addr or ""))


def junk_reason(addr: str):
    """Return a reason string if the address is a placeholder/tracker/file name, else None."""
    a = clean(addr)
    if "@" not in a:
        return "not an email address"
    local, domain = a.rsplit("@", 1)
    tld = domain.rsplit(".", 1)[-1]
    if tld in FILE_TLDS:
        return "looks like a file name, not an email"
    if domain in JUNK_DOMAINS or domain.endswith(".wixpress.com") or "sentry" in domain:
        return f"placeholder/tracking domain ({domain})"
    if local in JUNK_LOCAL:
        return f"placeholder or no-reply address ({local}@)"
    if re.fullmatch(r"[0-9a-f]{16,}", local):
        return "random hash, not a real mailbox"
    if len(a) > 80:
        return "too long to be a real address"
    return None


def extract(text: str):
    """Find candidate emails in free text, cleaned, de-duplicated, junk removed (order kept)."""
    out = []
    for m in EMAIL_RE.findall(text or ""):
        a = clean(m)
        if is_valid(a) and not junk_reason(a) and a not in out:
            out.append(a)
    return out


def _name_tokens(name: str):
    name = re.sub(r"\(.*?\)", " ", name or "")
    toks = [t.lower() for t in re.findall(r"[A-Za-z]+", name)]
    return [t for t in toks if t not in {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "jr", "sr"}]


BUSINESS_STOPWORDS = {"the", "and", "ltd", "limited", "inc", "llc", "llp", "plc", "company", "co", "group", "services",
                      "service", "uk", "of", "for", "solutions"}


def classify(addr: str, contact_name: str = "", model_kind: str = "", extra_generic=(), business_name: str = "") -> str:
    """Return 'generic' or 'named'.

    1. Matches the chosen contact's name  -> named   (john@, jsmith@, john.smith@)
    2. Role/shared mailbox                 -> generic (info@, sales@, enquiries.uk@)
    3. The researcher's label, if given
    4. Contains the business name          -> generic (acmeplumbing@gmail.com)
    5. Otherwise 'named'.
    """
    local = clean(addr).split("@", 1)[0]
    tokens = [t for t in re.split(r"[^a-z]+", local) if t]
    joined = "".join(tokens)

    nt = _name_tokens(contact_name)
    if nt:
        first, last = nt[0], nt[-1]
        variants = {first, last, first + last, last + first, first[0] + last, first + last[0]}
        if len(nt) == 1:
            variants = {first}
        if any(t in variants for t in tokens if len(t) >= 2) or joined in variants:
            return "named"

    generic = GENERIC_LOCAL | {g.lower() for g in extra_generic}
    if joined in generic or any(t in generic for t in tokens):
        return "generic"
    prefixes = GENERIC_PREFIXES + tuple(g.lower() for g in extra_generic)
    if any(joined.startswith(p.replace("-", "")) for p in prefixes):
        return "generic"

    if model_kind in ("generic", "named"):
        return model_kind
    biz = [t for t in re.findall(r"[a-z]+", (business_name or "").lower()) if len(t) >= 4 and t not in BUSINESS_STOPWORDS]
    if biz and any(t in joined for t in biz):
        return "generic"
    return "named"


def decode_cfemail(hexstr: str):
    """Decode a Cloudflare 'email-protection' string (data-cfemail / #hash)."""
    try:
        hexstr = hexstr.strip()
        key = int(hexstr[:2], 16)
        return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))
    except (ValueError, IndexError):
        return None
