"""Intake contracts learned from reading real competition sites.

Every case here reproduces something that actually happened against a live
host on 2026-09-14: an interstitial served in place of a page, a page that
merely embeds a bot-protection script, a script-rendered shell, and a
hackathon that publishes its deadline only as prose with a year.
"""

import io
from pathlib import Path
from uuid import uuid4

import pytest

from hackathon_competitor.capabilities import research
from hackathon_competitor.capabilities.research import (
    SourceFetcher,
    SourceUnreadable,
    discover_sources,
    extract_spec,
    parse_source,
)


class _Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200, headers: dict[str, str] | None = None):
        super().__init__(body)
        self.status = status
        self.headers = _Headers(headers or {})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class _Headers(dict):
    def get_content_charset(self):
        return "utf-8"


def _serve(monkeypatch, body: bytes, status: int = 200):
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = dict(request.headers)
        return _Response(body, status)

    monkeypatch.setattr(research, "urlopen", fake_urlopen)
    return captured


def test_interstitial_status_is_unreadable_not_an_empty_page(monkeypatch):
    _serve(monkeypatch, b"", status=202)
    with pytest.raises(SourceUnreadable) as caught:
        SourceFetcher().fetch("https://example.test/rules")
    assert caught.value.reason == "http_status"


def test_empty_body_is_unreadable(monkeypatch):
    _serve(monkeypatch, b"   \n ")
    with pytest.raises(SourceUnreadable) as caught:
        SourceFetcher().fetch("https://example.test/rules")
    assert caught.value.reason == "empty_body"


def test_javascript_challenge_stub_is_reported_as_a_challenge(monkeypatch):
    stub = b"<html><head><script>window.gokuProps = {};</script></head><body></body></html>"
    _serve(monkeypatch, stub)
    with pytest.raises(SourceUnreadable) as caught:
        SourceFetcher().fetch("https://example.test/rules")
    assert caught.value.reason == "bot_challenge"


def test_a_real_page_that_merely_embeds_bot_protection_is_still_read(monkeypatch):
    """The regression that matters: a served rules page is not a challenge.

    Devpost's rules pages carry the AWS WAF cookie helper inline.  Treating
    that script as proof of an interstitial discarded 120KB of real rules.
    """

    body = (
        b"<html><body><script>window.awsWafCookieDomainList = ['devpost.com'];</script>"
        + b"<p>Entrants must submit a public repository.</p>" * 400
        + b"</body></html>"
    )
    _serve(monkeypatch, body)
    content = SourceFetcher().fetch("https://example.test/rules")
    assert "public repository" in content


def test_fetch_advertises_a_general_accept_header(monkeypatch):
    captured = _serve(monkeypatch, b"<html><body><p>rules</p></body></html>")
    SourceFetcher().fetch("https://example.test/rules")
    assert captured["headers"]["Accept"] == "*/*"


def test_script_rendered_shell_is_unreadable_rather_than_ruleless(monkeypatch):
    _serve(monkeypatch, b"<html><body><div id='site'></div></body></html>")
    with pytest.raises(SourceUnreadable) as caught:
        discover_sources("https://example.test/competition")
    assert caught.value.reason == "no_extractable_text"


def test_unreadable_related_link_becomes_uncertainty_not_a_dead_mission(tmp_path):
    index = tmp_path / "index.html"
    rules = tmp_path / "rules.html"
    index.write_text(
        """<html><body data-hackathon-name="Test Cup">
        <p>Entrants must publish a public repository to be eligible.</p>
        <p>Submissions must include a runnable demo and a README.</p>
        <p>Entrants must not fabricate usage numbers.</p>
        <a data-source-authority="community" data-source-type="discussion"
           href="rules.html">Discussion</a>
        </body></html>""",
        encoding="utf-8",
    )
    rules.write_text("x", encoding="utf-8")

    class Fetcher(SourceFetcher):
        def fetch(self, uri, *, timeout=20.0):
            if uri.endswith("rules.html"):
                raise SourceUnreadable(uri, "bot_challenge", "interstitial")
            return super().fetch(uri, timeout=timeout)

    sources = discover_sources(str(index), fetcher=Fetcher())
    assert len(sources) == 1
    spec, _, _ = extract_spec(uuid4(), sources)
    assert any("could not be read" in note for note in spec.uncertainty)


def test_prose_submission_period_with_a_year_yields_a_typed_deadline():
    """The shape three live Devpost hackathons published on 2026-09-14."""

    source = parse_source(
        """<html><body data-hackathon-name="Agents for Humans">
        <p>Submission Period: Monday, August 10, 2026 (9:00 am Pacific Time)
           &ndash; Monday, September 14, 2026 (5:00 pm Pacific Time).</p>
        <p>Winners Announced: On or around Wednesday, October 14, 2026 (2:00 pm Pacific Time).</p>
        </body></html>""",
        "https://example.test/rules",
        "official",
        "official_page",
    )

    assert source.deadlines["SUBMISSION_DEADLINE"] == "2026-09-14T17:00:00-07:00"
    assert source.deadlines["RESULT"] == "2026-10-14T14:00:00-07:00"
    assert source.deadline == "2026-09-14T17:00:00-07:00"


def test_a_prose_deadline_without_a_time_stays_uncertain():
    source = parse_source(
        """<html><body>
        <p>Submission deadline: September 30, 2026.</p>
        </body></html>""",
        "https://example.test/rules",
        "official",
        "official_page",
    )

    assert "SUBMISSION_DEADLINE" not in source.deadlines
    assert any("without a time" in note for note in source.uncertainty)


def test_local_fixture_paths_still_load():
    fixture = Path(__file__).parent / "fixtures/generic_hackathon/index.html"
    assert SourceFetcher().fetch(str(fixture.resolve())).startswith("<!doctype html>")
