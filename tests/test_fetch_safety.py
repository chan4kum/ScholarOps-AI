from opportunity_intel.discovery.fetch import is_fetchable_url


def test_only_public_http_urls_are_fetchable() -> None:
    assert is_fetchable_url("https://euraxess.ec.europa.eu/jobs/123")
    assert is_fetchable_url("http://www.findaphd.com/phds/project/1")
    assert not is_fetchable_url("file:///etc/passwd")
    assert not is_fetchable_url("ftp://example.com/a")
    assert not is_fetchable_url("http://localhost:8000/admin")
    assert not is_fetchable_url("http://127.0.0.1:6379/")
    assert not is_fetchable_url("not-a-url")
