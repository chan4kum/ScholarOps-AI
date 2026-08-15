"""Tests for discovery extraction helpers and all 18 source parsers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from opportunity_intel.discovery.extract import extract_local
from opportunity_intel.discovery.web_search import is_skipped_url, unwrap_url

# Shared patch target constants to keep lines within the 100-char limit
_HTTPX_GET = "opportunity_intel.discovery.sources.httpx.get"
_FP_PARSE = "opportunity_intel.discovery.sources.feedparser.parse"

# ---------------------------------------------------------------------------
# Existing tests (unchanged)
# ---------------------------------------------------------------------------


def test_extract_json_ld_job_posting() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@type": "JobPosting",
      "title": "PhD in Agentic AI Governance",
      "hiringOrganization": {"name": "TU Delft"},
      "jobLocation": {"address": {"addressCountry": "NL"}},
      "validThrough": "2026-10-15",
      "description": "Fully funded 4-year PhD on autonomous agents."
    }
    </script>
    </head><body><h1>PhD in Agentic AI Governance</h1></body></html>
    """
    listing = extract_local("https://www.tudelft.nl/jobs/phd", html, source="test")
    assert listing is not None
    assert listing.country_code == "NL"
    assert listing.deadline is not None
    assert "funded" in listing.funding.lower() or "funded" in listing.summary.lower()


def test_extract_rejects_non_phd() -> None:
    html = (
        "<html><body><h1>Bachelor internship in marketing</h1>"
        "<p>Unpaid internship.</p></body></html>"
    )
    assert extract_local("https://example.com/job", html, source="test") is None


def test_unwrap_duckduckgo_redirect() -> None:
    wrapped = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Feuraxess.ec.europa.eu%2Fjobs%2F123"
    assert unwrap_url(wrapped) == "https://euraxess.ec.europa.eu/jobs/123"


def test_skip_linkedin() -> None:
    assert is_skipped_url("https://www.linkedin.com/jobs/view/1")
    assert not is_skipped_url("https://euraxess.ec.europa.eu/jobs/1")


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_rss_feed(entries: list[dict]) -> object:
    """Build a minimal feedparser-like result from a list of entry dicts."""

    class _Entry:
        def __init__(self, data: dict) -> None:
            self.title = data.get("title", "")
            self.link = data.get("link", "")
            self.author = data.get("author", "")
            self.summary = data.get("summary", "")
            self.published = data.get("published", "")
            self.tags = data.get("tags", [])

    class _Feed:
        def __init__(self) -> None:
            self.entries = [_Entry(e) for e in entries]

    return _Feed()


def _mock_html_response(html: str) -> MagicMock:
    mock = MagicMock()
    mock.text = html
    mock.raise_for_status = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# Source 3: AcademicTransfer (RSS)
# ---------------------------------------------------------------------------


def test_search_academictransfer_parses_rss() -> None:
    from opportunity_intel.discovery.sources import search_academictransfer

    fake_feed = _make_rss_feed(
        [
            {
                "title": "PhD in Responsible AI",
                "link": "https://www.academictransfer.com/en/jobs/12345/",
                "author": "Delft University of Technology",
                "summary": "Fully funded 4-year PhD position.",
                "published": "Mon, 01 Sep 2025 09:00:00 +0000",
            },
        ]
    )
    with patch(_FP_PARSE, return_value=fake_feed):
        listings = search_academictransfer("agentic AI PhD")

    assert len(listings) == 1
    assert listings[0].source == "academictransfer"
    assert listings[0].title == "PhD in Responsible AI"
    assert listings[0].deadline is not None


def test_search_academictransfer_empty_on_error() -> None:
    from opportunity_intel.discovery.sources import search_academictransfer

    with patch(
        "opportunity_intel.discovery.sources.feedparser.parse",
        side_effect=Exception("network error"),
    ):
        assert search_academictransfer("PhD AI") == []


# ---------------------------------------------------------------------------
# Source 5: AcademicPositions (RSS)
# ---------------------------------------------------------------------------


def test_search_academicpositions_parses_rss() -> None:
    from opportunity_intel.discovery.sources import search_academicpositions

    fake_feed = _make_rss_feed(
        [
            {
                "title": "PhD Position in AI Governance",
                "link": "https://academicpositions.eu/ad/56789",
                "author": "KTH Royal Institute",
                "summary": "Fully funded doctoral position in Sweden.",
                "published": "Wed, 10 Sep 2025 08:00:00 +0000",
            }
        ]
    )
    with patch(_FP_PARSE, return_value=fake_feed):
        listings = search_academicpositions("AI governance PhD")

    assert len(listings) == 1
    assert listings[0].source == "academicpositions"
    assert listings[0].title == "PhD Position in AI Governance"


# ---------------------------------------------------------------------------
# Source 4: PhDportal (HTML)
# ---------------------------------------------------------------------------


def test_search_phdportal_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_phdportal

    html = """
    <html><body><ul>
      <li class="item">
        <a class="item-title" href="/phd/42/phd-agentic-ai/">PhD in Agentic AI</a>
        <span class="university-name">Radboud University</span>
        <span class="country-name">Netherlands</span>
      </li>
    </ul></body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_phdportal("agentic AI")

    assert len(listings) == 1
    assert listings[0].source == "phdportal"
    assert listings[0].title == "PhD in Agentic AI"
    assert listings[0].source_url == "https://www.phdportal.eu/phd/42/phd-agentic-ai/"


def test_search_phdportal_empty_on_http_error() -> None:
    from opportunity_intel.discovery.sources import search_phdportal

    with patch(_HTTPX_GET, side_effect=httpx.ConnectError("unreachable")):
        assert search_phdportal("PhD NL") == []


# ---------------------------------------------------------------------------
# Source 6: AcademicKeys (HTML)
# ---------------------------------------------------------------------------


def test_search_academickeys_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_academickeys

    html = """
    <html><body><table>
      <tr class="jobRow">
        <td><a href="/all/go.php?do=jobdetail&id=111">PhD in Agentic AI</a></td>
        <td class="institution">University of Waterloo</td>
        <td class="location">Canada</td>
      </tr>
    </table></body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_academickeys("agentic AI PhD")

    assert len(listings) == 1
    assert listings[0].source == "academickeys"
    assert listings[0].organization == "University of Waterloo"


def test_search_academickeys_empty_on_error() -> None:
    from opportunity_intel.discovery.sources import search_academickeys

    with patch(_HTTPX_GET, side_effect=httpx.ConnectError("unreachable")):
        assert search_academickeys("PhD") == []


# ---------------------------------------------------------------------------
# Source 7: MyScience (RSS)
# ---------------------------------------------------------------------------


def test_search_myscience_parses_rss() -> None:
    from opportunity_intel.discovery.sources import search_myscience

    fake_feed = _make_rss_feed(
        [
            {
                "title": "PhD in Responsible AI — ETH Zurich",
                "link": "https://www.myscience.org/jobs/999",
                "author": "ETH Zurich",
                "summary": "Fully funded 4-year position at ETH.",
            }
        ]
    )
    with patch(_FP_PARSE, return_value=fake_feed):
        listings = search_myscience("AI governance PhD")

    assert len(listings) == 1
    assert listings[0].source == "myscience"
    assert "ETH" in listings[0].title


# ---------------------------------------------------------------------------
# Source 8: Jobs.ac.uk (HTML)
# ---------------------------------------------------------------------------


def test_search_jobs_ac_uk_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_jobs_ac_uk

    html = """
    <html><body>
      <div class="j-search-result">
        <h2><a class="j-search-result__title"
               href="/jobs/12345/phd-ai-governance">PhD in AI Governance</a></h2>
        <span class="j-search-result__employer">University of Manchester</span>
        <span class="j-search-result__location">Manchester, United Kingdom</span>
      </div>
    </body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_jobs_ac_uk("AI PhD")

    assert len(listings) == 1
    assert listings[0].source == "jobs_ac_uk"
    assert listings[0].source_url == "https://www.jobs.ac.uk/jobs/12345/phd-ai-governance"
    assert listings[0].funding == "funded studentship"
    assert listings[0].location == "Manchester, United Kingdom"


def test_search_jobs_ac_uk_empty_on_error() -> None:
    from opportunity_intel.discovery.sources import search_jobs_ac_uk

    with patch(_HTTPX_GET, side_effect=httpx.ConnectError("unreachable")):
        assert search_jobs_ac_uk("PhD") == []


# ---------------------------------------------------------------------------
# Source 9: DAAD (HTML)
# ---------------------------------------------------------------------------


def test_search_daad_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_daad

    html = """
    <html><body>
      <li class="scholarship-item">
        <a href="/en/study-and-research-in-germany/scholarships/daad-scholarship-database/123">
          DAAD Research Grant for Doctoral Candidates
        </a>
      </li>
    </body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_daad("PhD AI Germany")

    assert len(listings) == 1
    assert listings[0].source == "daad"
    assert listings[0].location == "Germany"
    assert listings[0].funding == "DAAD scholarship"


# ---------------------------------------------------------------------------
# Source 10: Jobbnorge (HTML)
# ---------------------------------------------------------------------------


def test_search_jobbnorge_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_jobbnorge

    html = """
    <html><body>
      <li class="job">
        <h2><a href="/jobs/567/phd-fellowship-ai">PhD Research Fellowship in AI</a></h2>
        <span class="employer">University of Oslo</span>
      </li>
    </body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_jobbnorge("PhD AI Norway")

    assert len(listings) == 1
    assert listings[0].source == "jobbnorge"
    assert listings[0].location == "Norway"
    assert listings[0].funding == "salaried fellowship"


# ---------------------------------------------------------------------------
# Source 11: WorkInDenmark (HTML)
# ---------------------------------------------------------------------------


def test_search_workindenmark_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_workindenmark

    html = """
    <html><body>
      <li class="job-result">
        <h2><a href="/job/678/industrial-phd-ai">Industrial PhD in AI</a></h2>
        <span class="company">DTU</span>
      </li>
    </body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_workindenmark("PhD AI Denmark")

    assert len(listings) == 1
    assert listings[0].source == "workindenmark"
    assert listings[0].location == "Denmark"
    assert listings[0].funding == "salaried position"


# ---------------------------------------------------------------------------
# Source 12: ScholarshipDb (HTML)
# ---------------------------------------------------------------------------


def test_search_scholarshipdb_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_scholarshipdb

    html = """
    <html><body>
      <li class="scholarship">
        <a class="scholarship-title" href="/scholarships/phd-ai-netherlands">
          PhD Scholarship in AI — Netherlands
        </a>
        <span class="country">Netherlands</span>
      </li>
    </body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_scholarshipdb("PhD AI")

    assert len(listings) == 1
    assert listings[0].source == "scholarshipdb"
    assert listings[0].funding == "scholarship"


# ---------------------------------------------------------------------------
# Source 13: Nature Careers (RSS)
# ---------------------------------------------------------------------------


def test_search_nature_careers_parses_rss() -> None:
    from opportunity_intel.discovery.sources import search_nature_careers

    fake_feed = _make_rss_feed(
        [
            {
                "title": "PhD in AI Ethics — Broad Institute",
                "link": "https://www.nature.com/naturecareers/jobs/88888",
                "author": "Broad Institute",
                "summary": "Fully funded doctoral position in computational AI ethics.",
            }
        ]
    )
    with patch(_FP_PARSE, return_value=fake_feed):
        listings = search_nature_careers("AI ethics PhD")

    assert len(listings) == 1
    assert listings[0].source == "nature_careers"


# ---------------------------------------------------------------------------
# Source 14: Science Careers (RSS)
# ---------------------------------------------------------------------------


def test_search_science_careers_parses_rss() -> None:
    from opportunity_intel.discovery.sources import search_science_careers

    fake_feed = _make_rss_feed(
        [
            {
                "title": "Graduate Research Assistantship in AI Governance",
                "link": "https://jobs.sciencecareers.org/job/77777",
                "author": "Stanford University",
                "summary": "NSF-funded doctoral assistantship.",
            }
        ]
    )
    with patch(_FP_PARSE, return_value=fake_feed):
        listings = search_science_careers("AI governance PhD")

    assert len(listings) == 1
    assert listings[0].source == "science_careers"


# ---------------------------------------------------------------------------
# Source 15: HigherEdJobs (HTML)
# ---------------------------------------------------------------------------


def test_search_higheredjobs_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_higheredjobs

    html = """
    <html><body>
      <div class="job-item">
        <h2><a class="job-title" href="/details.cfm?JobCode=55555">
          PhD Research Assistantship in Agentic AI
        </a></h2>
        <span class="institution">MIT</span>
        <span class="location">Cambridge, MA</span>
      </div>
    </body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_higheredjobs("agentic AI PhD")

    assert len(listings) == 1
    assert listings[0].source == "higheredjobs"
    assert listings[0].organization == "MIT"


# ---------------------------------------------------------------------------
# Source 16: ProFellow (HTML)
# ---------------------------------------------------------------------------


def test_search_profellow_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_profellow

    html = """
    <html><body>
      <article class="fellowship">
        <h2><a href="https://www.profellow.com/fellowship/nsf-grfp/">
          NSF Graduate Research Fellowship (GRFP)
        </a></h2>
      </article>
    </body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_profellow("AI PhD fellowship")

    assert len(listings) == 1
    assert listings[0].source == "profellow"
    assert listings[0].funding == "fully funded fellowship"


# ---------------------------------------------------------------------------
# Source 17: ResearchTweet (RSS)
# ---------------------------------------------------------------------------


def test_search_researchtweet_parses_rss() -> None:
    from opportunity_intel.discovery.sources import search_researchtweet

    fake_feed = _make_rss_feed(
        [
            {
                "title": "Funded PhD in Responsible AI — TU/e",
                "link": "https://researchtweet.com/funded-phd-responsible-ai-tue/",
                "summary": "Fully funded 4-year PhD at Eindhoven University.",
            }
        ]
    )
    with patch(_FP_PARSE, return_value=fake_feed):
        listings = search_researchtweet("responsible AI PhD")

    assert len(listings) == 1
    assert listings[0].source == "researchtweet"


# ---------------------------------------------------------------------------
# Source 18: FellowshipBard (HTML)
# ---------------------------------------------------------------------------


def test_search_fellowshipbard_parses_html() -> None:
    from opportunity_intel.discovery.sources import search_fellowshipbard

    html = """
    <html><body>
      <article class="post">
        <h2><a href="https://www.fellowshipbard.com/fellowship/ai-governance-phd/">
          AI Governance PhD Fellowship — Fully Funded
        </a></h2>
      </article>
    </body></html>
    """
    with patch(_HTTPX_GET, return_value=_mock_html_response(html)):
        listings = search_fellowshipbard("AI governance fellowship")

    assert len(listings) == 1
    assert listings[0].source == "fellowshipbard"
    assert listings[0].funding == "fellowship"


# ---------------------------------------------------------------------------
# ALL_SOURCE_FUNCTIONS registry test
# ---------------------------------------------------------------------------


def test_all_source_functions_registry() -> None:
    """ALL_SOURCE_FUNCTIONS has exactly 18 entries, all callable."""
    from opportunity_intel.discovery.sources import ALL_SOURCE_FUNCTIONS

    assert len(ALL_SOURCE_FUNCTIONS) == 18
    for fn in ALL_SOURCE_FUNCTIONS:
        assert callable(fn), f"{fn} is not callable"

    # Confirm all expected sources are present
    names = {fn.__name__ for fn in ALL_SOURCE_FUNCTIONS}
    expected = {
        "search_euraxess",
        "search_findaphd",
        "search_academictransfer",
        "search_phdportal",
        "search_academicpositions",
        "search_academickeys",
        "search_myscience",
        "search_jobs_ac_uk",
        "search_daad",
        "search_jobbnorge",
        "search_workindenmark",
        "search_scholarshipdb",
        "search_nature_careers",
        "search_science_careers",
        "search_higheredjobs",
        "search_profellow",
        "search_researchtweet",
        "search_fellowshipbard",
    }
    assert names == expected


# ---------------------------------------------------------------------------
# Pipeline wiring test — _search_rss calls all sources
# ---------------------------------------------------------------------------


def test_pipeline_search_rss_calls_all_sources() -> None:
    """_search_rss calls all sources in ALL_SOURCE_FUNCTIONS except search_findaphd."""
    from opportunity_intel.discovery import pipeline, sources
    from opportunity_intel.discovery.sources import ALL_SOURCE_FUNCTIONS, RawListing

    def _fake_listing(source: str) -> list[RawListing]:
        return [
            RawListing(
                title=f"PhD test {source}",
                source_url=f"https://{source}.example.com/1",
                organization="Org",
                location="NL",
                summary="Funded",
                source=source,
            )
        ]

    patches = {}
    for fn in ALL_SOURCE_FUNCTIONS:
        src = fn.__name__.replace("search_", "")
        patches[fn.__name__] = patch.object(sources, fn.__name__, return_value=_fake_listing(src))

    with (
        patches["search_euraxess"],
        patches["search_findaphd"],
        patches["search_academictransfer"],
        patches["search_phdportal"],
        patches["search_academicpositions"],
        patches["search_academickeys"],
        patches["search_myscience"],
        patches["search_jobs_ac_uk"],
        patches["search_daad"],
        patches["search_jobbnorge"],
        patches["search_workindenmark"],
        patches["search_scholarshipdb"],
        patches["search_nature_careers"],
        patches["search_science_careers"],
        patches["search_higheredjobs"],
        patches["search_profellow"],
        patches["search_researchtweet"],
        patches["search_fellowshipbard"],
    ):
        result = pipeline._search_rss("funded PhD AI", {})

    # search_findaphd is excluded from _search_rss (added separately in discover())
    result_sources = {item.source for item in result}
    assert "euraxess" in result_sources
    assert "academictransfer" in result_sources
    assert "jobs_ac_uk" in result_sources
    assert "daad" in result_sources
    assert "nature_careers" in result_sources
    # findaphd must NOT be in _search_rss output
    assert "findaphd" not in result_sources
