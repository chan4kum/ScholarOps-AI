"""Discovery source parsers — one function per board.

All functions follow the same contract:
  - Accept a query string
  - Return list[RawListing] (empty on any failure)
  - Never raise — callers expect graceful degradation
  - Never call an LLM — structured parsing only

Source inventory (20 total):
  RSS/Atom feeds (no HTML parse needed):
    1.  EURAXESS          euraxess.ec.europa.eu
    3.  AcademicTransfer  academictransfer.com
    5.  AcademicPositions academicpositions.eu
    7.  MyScience         myscience.org
    14. Nature Careers    nature.com/naturecareers
    15. Science Careers   jobs.sciencecareers.org
    18. ResearchTweet     researchtweet.com

  HTML scrapers (selectolax, best-effort):
    2.  FindAPhD          findaphd.com
    4.  PhDportal         phdportal.eu / phdportal.com
    6.  AcademicKeys      academickeys.com
    8.  Jobs.ac.uk        jobs.ac.uk/phd
    9.  DAAD              daad.de/en/study-and-research-in-germany
   10.  Jobbnorge         jobbnorge.no
   11.  WorkInDenmark     workindenmark.dk
   12.  ScholarshipDb     scholarshipdb.net
   13.  HigherEdJobs      higheredjobs.com
   16.  ProFellow         profellow.com
   17.  FellowshipBard    fellowshipbard.com

  Excluded (ToS / no public search API):
    -   ResearchGate Jobs  (ToS restricted — in skip_domains)
    -   Campus France      (French-only, no programmatic search)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import httpx

from opportunity_intel.scoring.rules import normalize_country

USER_AGENT = "OpportunityIntel/0.1 (personal research; local-first)"

# Shared HTTP timeout for all scrapers
_TIMEOUT = 20.0


@dataclass
class RawListing:
    title: str
    source_url: str
    organization: str
    location: str
    summary: str
    source: str
    funding: str = ""
    deadline: date | None = None
    supervisor: str = ""

    @property
    def country_code(self) -> str:
        return normalize_country(f"{self.location} {self.organization} {self.title}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_deadline(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, OverflowError):
        pass
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%b %d, %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[:40].strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_rss_feed(url: str, *, source: str, max_entries: int = 40) -> list[RawListing]:
    """Generic RSS/Atom parser. Returns empty list on any failure."""
    try:
        parsed = feedparser.parse(
            url,
            agent=USER_AGENT,
            request_headers={"User-Agent": USER_AGENT},
        )
    except Exception:  # noqa: BLE001
        return []
    listings: list[RawListing] = []
    for entry in parsed.entries[:max_entries]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue
        location = ""
        tags = getattr(entry, "tags", None) or []
        if tags:
            first = tags[0]
            location = first.get("term", "") if hasattr(first, "get") else str(first)
        listings.append(
            RawListing(
                title=title,
                source_url=link,
                organization=getattr(entry, "author", "") or "",
                location=location,
                summary=(getattr(entry, "summary", "") or "")[:1200],
                source=source,
                deadline=_parse_deadline(getattr(entry, "published", None)),
            )
        )
    return [item for item in listings if item.title and item.source_url]


def _get_html(url: str, *, params: dict | None = None, timeout: float = _TIMEOUT) -> str | None:
    """Fetch HTML with shared UA. Returns None on any HTTP error."""
    try:
        r = httpx.get(
            url,
            params=params,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        r.raise_for_status()
        return r.text
    except httpx.HTTPError:
        return None


def _html_parser(html: str):  # noqa: ANN201
    from selectolax.parser import HTMLParser

    return HTMLParser(html)


# ---------------------------------------------------------------------------
# Source 1: EURAXESS (RSS)
# ---------------------------------------------------------------------------


def search_euraxess(query: str) -> list[RawListing]:
    """EURAXESS RSS — EC official hub for funded European doctoral positions."""
    url = f"https://euraxess.ec.europa.eu/jobs/search.rss?keywords={quote_plus(query)}"
    parsed = feedparser.parse(url, agent=USER_AGENT, request_headers={"User-Agent": USER_AGENT})
    listings: list[RawListing] = []
    for entry in parsed.entries[:40]:
        location = ""
        tags = getattr(entry, "tags", None) or []
        if tags:
            first = tags[0]
            location = first.get("term", "") if hasattr(first, "get") else str(first)
        listings.append(
            RawListing(
                title=getattr(entry, "title", "").strip(),
                source_url=getattr(entry, "link", "").strip(),
                organization=getattr(entry, "author", "") or "",
                location=location,
                summary=getattr(entry, "summary", "") or "",
                source="euraxess",
                deadline=_parse_deadline(getattr(entry, "published", None)),
            )
        )
    return [item for item in listings if item.title and item.source_url]


# ---------------------------------------------------------------------------
# Source 2: FindAPhD (HTML scrape)
# ---------------------------------------------------------------------------


def search_findaphd(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """FindAPhD — major global database of advertised doctoral projects."""
    html = _get_html(
        "https://www.findaphd.com/phds/",
        params={"Keywords": query, "SearchType": 1},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for card in tree.css("div.phd-result, article, li.result")[:40]:
        link = card.css_first("a")
        if link is None or not link.attributes.get("href"):
            continue
        href = link.attributes["href"]
        if href.startswith("/"):
            href = "https://www.findaphd.com" + href
        title = (link.text() or "").strip()
        if not title:
            continue
        country_el = card.css_first(".phd-result__country, .country, .instCountry")
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization="",
                location=(country_el.text() if country_el is not None else "").strip(),
                summary=" ".join((card.text() or "").split())[:800],
                source="findaphd",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 3: AcademicTransfer (RSS — Dutch/European salaried PhD positions)
# ---------------------------------------------------------------------------


def search_academictransfer(query: str) -> list[RawListing]:
    """AcademicTransfer — official portal for Dutch university PhD jobs."""
    url = f"https://www.academictransfer.com/en/jobs/rss/?q={quote_plus(query)}&job_type=phd"
    return _parse_rss_feed(url, source="academictransfer")


# ---------------------------------------------------------------------------
# Source 4: PhDportal (HTML scrape — phdportal.eu / phdportal.com)
# ---------------------------------------------------------------------------


def search_phdportal(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """PhDportal — worldwide PhD/doctoral programmes including fully funded."""
    html = _get_html(
        "https://www.phdportal.eu/search/",
        params={"keywords": query, "limit": 40},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    cards = (
        tree.css("li.item, div.item, article.programme-card, div.programme-item")[:40]
        or tree.css("li, article")[:40]
    )
    for card in cards:
        link_el = card.css_first(
            "a.item-title, h3 a, h2 a, .programme-title a, a.title, a[href*='/phd/']"
        )
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.phdportal.eu" + href
        title = (link_el.text() or "").strip()
        if not title:
            continue
        org_el = card.css_first(".item-institute, .university-name, .institute-name, .organisation")
        loc_el = card.css_first(".item-country, .country-name, .country, .location")
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization=(org_el.text() if org_el else "").strip(),
                location=(loc_el.text() if loc_el else "").strip(),
                summary=" ".join((card.text() or "").split())[:800],
                source="phdportal",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 5: AcademicPositions (RSS — pan-European academic vacancies)
# ---------------------------------------------------------------------------


def search_academicpositions(query: str) -> list[RawListing]:
    """AcademicPositions.eu — European salaried PhD and research vacancies."""
    url = f"https://academicpositions.eu/feed?type=phd&keywords={quote_plus(query)}"
    return _parse_rss_feed(url, source="academicpositions")


# ---------------------------------------------------------------------------
# Source 6: AcademicKeys (HTML scrape — North American + international)
# ---------------------------------------------------------------------------


def search_academickeys(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """AcademicKeys — graduate/PhD positions including North American universities."""
    html = _get_html(
        "https://www.academickeys.com/all/go.php",
        params={"do": "findJob", "type": "Grad_Studies", "q": query},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for row in tree.css("tr.jobRow, tr.odd, tr.even, div.jobListing, li.job")[:40]:
        link_el = row.css_first("a[href*='jobdetail'], a[href*='job'], td a, a.jobTitle")
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.academickeys.com" + href
        elif not href.startswith("http"):
            continue
        title = (link_el.text() or "").strip()
        if not title:
            continue
        org_el = row.css_first("td.institution, .institution, td:nth-child(2)")
        loc_el = row.css_first("td.location, .location, td:nth-child(3)")
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization=(org_el.text() if org_el else "").strip(),
                location=(loc_el.text() if loc_el else "").strip(),
                summary=" ".join((row.text() or "").split())[:800],
                source="academickeys",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 7: MyScience (RSS — CH/DE/AT/FR research openings)
# ---------------------------------------------------------------------------


def search_myscience(query: str) -> list[RawListing]:
    """MyScience.org — RSS feed for research vacancies in Switzerland, Germany, Austria, France."""
    url = f"https://www.myscience.org/rss/jobs.rss?q={quote_plus(query)}&type=phd"
    return _parse_rss_feed(url, source="myscience")


# ---------------------------------------------------------------------------
# Source 8: Jobs.ac.uk (HTML scrape — UK funded studentships)
# ---------------------------------------------------------------------------


def search_jobs_ac_uk(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """Jobs.ac.uk — primary UK board for funded PhD studentships and DTPs."""
    html = _get_html(
        "https://www.jobs.ac.uk/search/",
        params={"keywords": query, "type": "phd", "per_page": 30},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for card in tree.css("div.j-search-result, article.result, li.search-result, div.result-item")[
        :40
    ]:
        link_el = card.css_first("h2 a, h3 a, a.j-search-result__title, a.result-title")
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.jobs.ac.uk" + href
        title = (link_el.text() or "").strip()
        if not title:
            continue
        org_el = card.css_first(
            ".j-search-result__employer, .employer, .institution, .organisation-name"
        )
        loc_el = card.css_first(".j-search-result__location, .location, .place")
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization=(org_el.text() if org_el else "").strip(),
                location=(loc_el.text() if loc_el else "United Kingdom").strip(),
                summary=" ".join((card.text() or "").split())[:800],
                source="jobs_ac_uk",
                funding="funded studentship",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 9: DAAD (HTML scrape — German scholarships for international PhDs)
# ---------------------------------------------------------------------------


def search_daad(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """DAAD scholarship database — full funding for international doctoral candidates in Germany."""
    html = _get_html(
        "https://www.daad.de/en/study-and-research-in-germany/scholarships/daad-scholarship-database/",
        params={"q": query, "target-group": "phd", "origin": "any"},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for card in tree.css(
        "li.scholarship-item, div.scholarship-card, article.scholarship, div.result-item"
    )[:30]:
        link_el = card.css_first("a[href*='daad'], h2 a, h3 a, a.scholarship-title")
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.daad.de" + href
        title = (link_el.text() or "").strip()
        if not title:
            continue
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization="DAAD",
                location="Germany",
                summary=" ".join((card.text() or "").split())[:800],
                source="daad",
                funding="DAAD scholarship",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 10: Jobbnorge (HTML scrape — Norwegian doctoral fellowships)
# ---------------------------------------------------------------------------


def search_jobbnorge(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """Jobbnorge — official Norwegian portal for salaried doctoral research fellowships."""
    html = _get_html(
        "https://www.jobbnorge.no/search/en",
        params={"q": query, "categories": "Research"},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for card in tree.css("li.job, div.job-listing, article.vacancy, div.search-result")[:30]:
        link_el = card.css_first("h2 a, h3 a, a.job-title, a.vacancy-title")
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.jobbnorge.no" + href
        title = (link_el.text() or "").strip()
        if not title:
            continue
        org_el = card.css_first(".employer, .institution, .organisation")
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization=(org_el.text() if org_el else "").strip(),
                location="Norway",
                summary=" ".join((card.text() or "").split())[:800],
                source="jobbnorge",
                funding="salaried fellowship",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 11: WorkInDenmark (HTML scrape — Danish PhD positions)
# ---------------------------------------------------------------------------


def search_workindenmark(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """WorkInDenmark — national portal for salaried Danish PhD and Industrial PhD positions."""
    html = _get_html(
        "https://www.workindenmark.dk/job-search/all-jobs",
        params={"search": query, "category": "PhD"},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for card in tree.css("li.job-result, div.job-card, article.job, div.vacancy")[:30]:
        link_el = card.css_first("h2 a, h3 a, a.job-title, a.position-title")
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.workindenmark.dk" + href
        title = (link_el.text() or "").strip()
        if not title:
            continue
        org_el = card.css_first(".company, .employer, .institution")
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization=(org_el.text() if org_el else "").strip(),
                location="Denmark",
                summary=" ".join((card.text() or "").split())[:800],
                source="workindenmark",
                funding="salaried position",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 12: ScholarshipDb (HTML scrape — global fellowship aggregator)
# ---------------------------------------------------------------------------


def search_scholarshipdb(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """ScholarshipDb.net — global search engine indexing PhD studentships and fellowships."""
    html = _get_html(
        "https://scholarshipdb.net/scholarships",
        params={"q": query, "for": "PhD"},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for card in tree.css("li.scholarship, div.scholarship-item, article.result, li.result")[:30]:
        link_el = card.css_first("a.scholarship-title, h2 a, h3 a, a[href*='/scholarships/']")
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://scholarshipdb.net" + href
        title = (link_el.text() or "").strip()
        if not title:
            continue
        loc_el = card.css_first(".country, .location, span.flag-label")
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization="",
                location=(loc_el.text() if loc_el else "").strip(),
                summary=" ".join((card.text() or "").split())[:800],
                source="scholarshipdb",
                funding="scholarship",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 13: Nature Careers (RSS — high-impact international research board)
# ---------------------------------------------------------------------------


def search_nature_careers(query: str) -> list[RawListing]:
    """Nature Careers RSS — funded PhD positions in STEM and life sciences worldwide."""
    url = f"https://www.nature.com/naturecareers/rss/jobs?q={quote_plus(query)}&type=phd"
    return _parse_rss_feed(url, source="nature_careers")


# ---------------------------------------------------------------------------
# Source 14: Science Careers / AAAS (RSS)
# ---------------------------------------------------------------------------


def search_science_careers(query: str) -> list[RawListing]:
    """Science/AAAS Careers RSS — academic openings and doctoral vacancies globally."""
    url = f"https://jobs.sciencecareers.org/rss/jobs?q={quote_plus(query)}&c=phd"
    return _parse_rss_feed(url, source="science_careers")


# ---------------------------------------------------------------------------
# Source 15: HigherEdJobs (HTML scrape — US graduate assistantships + international)
# ---------------------------------------------------------------------------


def search_higheredjobs(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """HigherEdJobs — graduate assistantships, fellowships, and university research positions."""
    html = _get_html(
        "https://www.higheredjobs.com/search/advanced_action.cfm",
        params={
            "PosType": "2",  # Graduate/Postdoctoral
            "Keyword": query,
            "NumJobs": 30,
        },
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for card in tree.css("div.job-item, li.job, article.position, tr.job-row")[:30]:
        link_el = card.css_first("a.job-title, h2 a, h3 a, td a[href*='details']")
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = "https://www.higheredjobs.com" + href
        title = (link_el.text() or "").strip()
        if not title:
            continue
        org_el = card.css_first(".institution, .employer, .college")
        loc_el = card.css_first(".location, .city-state")
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization=(org_el.text() if org_el else "").strip(),
                location=(loc_el.text() if loc_el else "USA").strip(),
                summary=" ".join((card.text() or "").split())[:800],
                source="higheredjobs",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 16: ProFellow (HTML scrape — fully funded doctoral program directory)
# ---------------------------------------------------------------------------


def search_profellow(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """ProFellow — directory of fully funded doctoral programs and national fellowships."""
    html = _get_html(
        "https://www.profellow.com/fellowships/",
        params={"s": query, "category": "doctoral"},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for card in tree.css("article.fellowship, div.fellowship-item, li.fellowship, div.post")[:30]:
        link_el = card.css_first("h2 a, h3 a, a.fellowship-title, a.entry-title")
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href or not href.startswith("http"):
            continue
        title = (link_el.text() or "").strip()
        if not title:
            continue
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization="",
                location="",
                summary=" ".join((card.text() or "").split())[:800],
                source="profellow",
                funding="fully funded fellowship",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Source 17: ResearchTweet (RSS — daily funded PhD aggregator)
# ---------------------------------------------------------------------------


def search_researchtweet(query: str) -> list[RawListing]:
    """ResearchTweet — aggregates daily funded PhD and postdoc vacancies worldwide."""
    url = f"https://researchtweet.com/feed/?s={quote_plus(query)}+PhD+funded"
    return _parse_rss_feed(url, source="researchtweet")


# ---------------------------------------------------------------------------
# Source 18: FellowshipBard (HTML scrape — international doctoral scholarships)
# ---------------------------------------------------------------------------


def search_fellowshipbard(query: str, *, timeout: float = _TIMEOUT) -> list[RawListing]:
    """FellowshipBard — curated platform indexing academic fellowships and doctoral scholarships."""
    html = _get_html(
        "https://www.fellowshipbard.com/",
        params={"s": query},
        timeout=timeout,
    )
    if not html:
        return []
    tree = _html_parser(html)
    listings: list[RawListing] = []
    for card in tree.css("article.post, div.fellowship-card, li.fellowship, div.entry")[:30]:
        link_el = card.css_first("h2 a, h3 a, a.entry-title, a.post-title")
        if link_el is None:
            continue
        href = (link_el.attributes.get("href") or "").strip()
        if not href or not href.startswith("http"):
            continue
        title = (link_el.text() or "").strip()
        if not title:
            continue
        listings.append(
            RawListing(
                title=title,
                source_url=href.split("?")[0],
                organization="",
                location="",
                summary=" ".join((card.text() or "").split())[:800],
                source="fellowshipbard",
                funding="fellowship",
            )
        )
    return listings


# ---------------------------------------------------------------------------
# Combined convenience entry point (no web search)
# Use pipeline.discover() for full web-search augmentation
# ---------------------------------------------------------------------------

# All 18 implemented sources in priority order
ALL_SOURCE_FUNCTIONS = [
    search_euraxess,  # 1  RSS  EU
    search_findaphd,  # 2  HTML global
    search_academictransfer,  # 3  RSS  NL/EU
    search_phdportal,  # 4  HTML global
    search_academicpositions,  # 5  RSS  EU
    search_academickeys,  # 6  HTML global
    search_myscience,  # 7  RSS  CH/DE/AT/FR
    search_jobs_ac_uk,  # 8  HTML UK
    search_daad,  # 9  HTML DE
    search_jobbnorge,  # 10 HTML NO
    search_workindenmark,  # 11 HTML DK
    search_scholarshipdb,  # 12 HTML global
    search_nature_careers,  # 13 RSS  global
    search_science_careers,  # 14 RSS  global
    search_higheredjobs,  # 15 HTML US
    search_profellow,  # 16 HTML US/global
    search_researchtweet,  # 17 RSS  global
    search_fellowshipbard,  # 18 HTML global
]


def discover(query: str) -> list[RawListing]:
    """All 18 structured sources deduplicated. Use pipeline.discover for web search."""
    seen: set[str] = set()
    combined: list[RawListing] = []
    for fn in ALL_SOURCE_FUNCTIONS:
        for listing in fn(query):
            if listing.source_url in seen:
                continue
            seen.add(listing.source_url)
            combined.append(listing)
    return combined
