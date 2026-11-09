"""Scan a business website: the homepage plus likely contact/about/team pages.

Pulls out emails (including Cloudflare-protected and "name [at] domain [dot] com" ones), social
links and lines that mention roles (owner, founder, marketing...). Saves each page's visible text
to a file so the researcher can read the relevant pages without loading raw HTML.
Standard library only.
"""
import re
import ssl
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import emails as em  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
PAGE_KEYWORDS = [  # (keyword in URL path or link text, score)
    ("contact", 10), ("get-in-touch", 9), ("getintouch", 9), ("about", 9), ("team", 9), ("meet", 8),
    ("staff", 8), ("people", 7), ("who-we-are", 8), ("whoweare", 8), ("leadership", 7), ("founder", 7),
    ("owner", 7), ("management", 6), ("directors", 6), ("our-story", 6), ("story", 4), ("enquir", 6),
    ("inquir", 6), ("find-us", 5), ("company", 3), ("history", 3),
]
GUESS_PATHS = ["/contact", "/contact-us", "/about", "/about-us"]
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|docx?|xlsx?|mp4|mp3|ics)$", re.I)
SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe"}
BLOCK_TAGS = {"p", "div", "section", "article", "header", "footer", "li", "ul", "ol", "tr", "td", "th", "table",
              "h1", "h2", "h3", "h4", "h5", "h6", "address", "nav", "aside", "main", "figure", "figcaption",
              "blockquote", "dd", "dt", "form", "label"}
ROLE_RE = re.compile(r"\b(owner|co-owner|founder|co-founder|proprietor|director|managing director|ceo|"
                     r"chief executive|president|principal|partner|marketing|manager|head of|broker|operator)\b", re.I)
OBFUSCATED_RE = re.compile(
    r"([a-z0-9._%+-]+)\s*(?:\[at\]|\(at\)|\{at\}|\s+at\s+(?=[a-z0-9-]+\s*(?:\[dot\]|\(dot\)|\{dot\})))\s*"
    r"([a-z0-9-]+(?:\s*(?:\[dot\]|\(dot\)|\{dot\}|\.)\s*[a-z0-9-]+)+)", re.I)
SOCIAL = {
    "facebook": re.compile(r"https?://(?:www\.|m\.|business\.)?(?:facebook|fb)\.com/(?:profile\.php\?id=\d+|"
                           r"(?!sharer|share|plugins|dialog|tr\b|policy|privacy|help|login|\d{4}/fbml)[^\s\"'<>?#]+)", re.I),
    "linkedin": re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|in|school)/[^\s\"'<>?#]+", re.I),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/(?!p/|reel/|explore/)[^\s\"'<>?#/]+", re.I),
}


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.cf = [], [], []
        self.title, self._in_title, self._skip, self._link = "", False, 0, None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in BLOCK_TAGS or tag == "br":
            self.parts.append("\n")
        if a.get("data-cfemail"):
            self.cf.append(a["data-cfemail"])
        if tag == "a":
            href = a.get("href", "")
            self._link = [href, []]
            self.links.append(self._link)
            if "/cdn-cgi/l/email-protection#" in href:
                self.cf.append(href.split("#", 1)[1])

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a":
            self._link = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._skip:
            return
        self.parts.append(data)
        if self._link is not None:
            self._link[1].append(data)

    def text(self):
        lines, prev = [], None
        for line in "".join(self.parts).split("\n"):
            line = re.sub(r"\s+", " ", line).strip()
            if line and line != prev:
                lines.append(line)
            prev = line
        return "\n".join(lines)


def _fetch(url, timeout=12):
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                                "Accept-Language": "en-GB,en;q=0.9", "Accept-Encoding": "identity"})
    insecure = False
    try:
        resp = urlopen(req, timeout=timeout, context=ssl.create_default_context())
    except URLError as e:
        if isinstance(getattr(e, "reason", None), ssl.SSLError):
            # Many small-business sites have expired certificates; read the public page anyway.
            resp = urlopen(req, timeout=timeout, context=ssl._create_unverified_context())
            insecure = True
        else:
            raise
    with resp:
        ctype = resp.headers.get("Content-Type", "")
        if ctype and "html" not in ctype and "text" not in ctype:
            return resp.geturl(), None, insecure
        body = resp.read(3_000_000)
        charset = resp.headers.get_content_charset()
        if not charset:
            m = re.search(rb'charset=["\']?([a-zA-Z0-9_-]+)', body[:3000])
            charset = m.group(1).decode() if m else "utf-8"
        try:
            return resp.geturl(), body.decode(charset, errors="replace"), insecure
        except LookupError:
            return resp.geturl(), body.decode("utf-8", errors="replace"), insecure


def _host(url):
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _canon(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", p.query, ""))


def _emails_from(html, parser, page_text):
    found = []
    for hexstr in parser.cf:
        dec = em.decode_cfemail(hexstr)
        if dec:
            found.append(dec)
    for href, _ in parser.links:
        if href.lower().startswith("mailto:"):
            found.append(unquote(href[7:]).split("?")[0])
    for m in OBFUSCATED_RE.finditer(page_text):
        domain = re.sub(r"\s*(?:\[dot\]|\(dot\)|\{dot\})\s*", ".", m.group(2)).replace(" ", "")
        found.append(f"{m.group(1)}@{domain}")
    found += em.EMAIL_RE.findall(page_text)
    found += em.EMAIL_RE.findall(html)
    out = []
    for a in found:
        a = em.clean(a)
        if em.is_valid(a) and not em.junk_reason(a) and a not in out:
            out.append(a)
    return out


def scan(url, out_dir=None, max_pages=8, time_budget=75):
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    started = time.time()
    result = {"start_url": url, "final_url": None, "reachable": False, "error": None, "insecure_ssl": False,
              "pages": [], "emails": {}, "social": {k: [] for k in SOCIAL}, "role_lines": [],
              "js_heavy_suspected": False}
    tried = [url] + ([url.replace("https://", "http://", 1)] if url.startswith("https://") else [])
    home = None
    for u in tried:
        try:
            final, html, insecure = _fetch(u)
            if html is None:
                result["error"] = "Homepage is not an HTML page."
                return result
            home = (final, html)
            result["insecure_ssl"] = insecure
            break
        except HTTPError as e:
            result["error"] = f"HTTP {e.code} from {u}"
        except Exception as e:  # DNS failure, timeout, refused...
            result["error"] = f"{type(e).__name__}: {e}"[:200]
    if not home:
        return result
    result["reachable"], result["error"], result["final_url"] = True, None, home[0]
    host = _host(home[0])

    queue = [(home[0], home[1], "home")]
    p0 = _Parser()
    p0.feed(home[1])
    candidates = {}
    for order, (href, words) in enumerate(p0.links):
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absu = urljoin(home[0], href)
        sp = urlsplit(absu)
        if sp.scheme not in ("http", "https") or _host(absu) != host or SKIP_EXT.search(sp.path):
            continue
        hay = (sp.path + " " + " ".join(words)).lower()
        score = max((s for k, s in PAGE_KEYWORDS if k in hay), default=0)
        key = _canon(absu)
        if score and key != _canon(home[0]) and (key not in candidates or candidates[key][0] < score):
            candidates[key] = (score, order, absu)
    picked = [v[2] for v in sorted(candidates.values(), key=lambda v: (-v[0], v[1]))][: max_pages - 1]
    if not any(re.search(r"contact|about", u, re.I) for u in picked):
        base = f"{urlsplit(home[0]).scheme}://{urlsplit(home[0]).netloc}"
        picked += [base + g for g in GUESS_PATHS][: max(0, max_pages - 1 - len(picked))]

    seen = {_canon(home[0])}
    for u in picked:
        if time.time() - started > time_budget:
            break
        if _canon(u) in seen:
            continue
        seen.add(_canon(u))
        try:
            final, html, _ = _fetch(u)
            if html and _canon(final) not in {_canon(q[0]) for q in queue}:
                queue.append((final, html, ""))
        except Exception:
            continue  # guessed pages that 404 are expected
        time.sleep(0.2)

    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
    for i, (u, html, label) in enumerate(queue, start=1):
        p = _Parser()
        p.feed(html)
        page_text = p.text()
        title = re.sub(r"\s+", " ", p.title).strip()
        page_emails = _emails_from(html, p, page_text)
        for a in page_emails:
            result["emails"].setdefault(a, []).append(u)
        for kind, rx in SOCIAL.items():
            for m in rx.findall(html):
                m = m.rstrip("/\\.,")
                if m not in result["social"][kind]:
                    result["social"][kind].append(m)
        for line in page_text.split("\n"):
            if 3 < len(line) <= 220 and ROLE_RE.search(line):
                entry = {"url": u, "line": line}
                if entry not in result["role_lines"] and len(result["role_lines"]) < 40:
                    result["role_lines"].append(entry)
        file = None
        if out_dir:
            slug = re.sub(r"[^a-z0-9]+", "-", (urlsplit(u).path or "home").lower()).strip("-")[:40] or "home"
            file = Path(out_dir) / f"{i:02d}_{slug}.txt"
            file.write_text(f"URL: {u}\nTITLE: {title}\n\n{page_text[:40000]}", encoding="utf-8")
        result["pages"].append({"url": u, "title": title, "chars": len(page_text), "emails": page_emails,
                                "file": str(file) if file else None})
    result["js_heavy_suspected"] = result["pages"][0]["chars"] < 300
    return result


if __name__ == "__main__":
    import json
    if len(sys.argv) < 2:
        print("usage: site_scan.py <url> [out_dir]")
        sys.exit(2)
    print(json.dumps(scan(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None), indent=2))
