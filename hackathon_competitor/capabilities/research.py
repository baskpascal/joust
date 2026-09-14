from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ..models import Evidence, HackathonSpec, Requirement

MAX_SOURCE_BYTES = 2_000_000
AUTHORITY_CONFIDENCE = {"official": 0.99, "sponsor": 0.9, "community": 0.35}


@dataclass(frozen=True)
class SourceLink:
    uri: str
    authority: str
    source_type: str


@dataclass
class ParsedSource:
    uri: str
    authority: str
    source_type: str
    title: str = ""
    organizer: str | None = None
    deadline: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    deadlines: dict[str, str] = field(default_factory=dict)
    deadline_claims: dict[str, str] = field(default_factory=dict)
    uncertainty: list[str] = field(default_factory=list)
    judging_mode: str | None = None
    leaderboard_model: str | None = None
    scoring_rules: list[str] = field(default_factory=list)
    rules: list[dict[str, str]] = field(default_factory=list)
    claims: list[dict[str, str]] = field(default_factory=list)
    links: list[SourceLink] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    text: str = ""


class SourceUnreadable(ValueError):
    """A source was reached but its content could not be honestly read.

    A page that answers with a bot interstitial, an error status, an empty
    body, or a script-only shell is *unread*, not *ruleless*.  Collapsing the
    two made Joust report "this competition publishes no rules" when the truth
    was "Joust never saw the page", so every such outcome is raised with a
    machine-readable reason and recorded as unreadable.
    """

    def __init__(self, uri: str, reason: str, detail: str = ""):
        self.uri = uri
        self.reason = reason
        self.detail = detail
        message = f"source unreadable ({reason}): {uri}"
        super().__init__(f"{message} — {detail}" if detail else message)


class SourceTooLarge(SourceUnreadable):
    def __init__(self, uri: str = "", detail: str = ""):
        super().__init__(uri, "too_large", detail or f"source exceeds {MAX_SOURCE_BYTES} bytes")


# Markers that appear only on an interstitial, never in a served page.  The
# generic vendor script (AWS WAF's cookie helper, say) is deliberately absent:
# real competition pages embed it too, and matching it classified a complete
# 120KB rules page as a bot challenge.
_CHALLENGE_MARKERS = (
    "window.gokuprops",
    "cf_chl_opt",
    "/cdn-cgi/challenge-platform",
    "enable javascript and cookies to continue",
    "checking your browser before accessing",
)
# A challenge document is a stub.  Anything substantial is a page, whatever
# scripts it happens to carry, so the size guard keeps the markers honest.
MAX_CHALLENGE_BYTES = 20_000
MIN_READABLE_TEXT = 400


def _challenge_reason(body: str) -> str | None:
    if len(body) > MAX_CHALLENGE_BYTES:
        return None
    lowered = body.lower()
    for marker in _CHALLENGE_MARKERS:
        if marker in lowered:
            return marker
    return None


class SourceFetcher:
    def fetch(self, uri: str, *, timeout: float = 20.0) -> str:
        local_candidate = Path(uri)
        if local_candidate.is_absolute():
            if local_candidate.stat().st_size > MAX_SOURCE_BYTES:
                raise SourceTooLarge(uri)
            return local_candidate.read_text(encoding="utf-8")
        parsed = urlparse(uri)
        if parsed.scheme in {"http", "https"}:
            return self._fetch_http(uri, timeout=timeout)
        if parsed.scheme == "file":
            path = Path(parsed.path)
        elif parsed.scheme == "":
            path = Path(uri)
        else:
            raise ValueError(f"unsupported source scheme: {parsed.scheme}")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise SourceTooLarge(uri)
        return path.read_text(encoding="utf-8")

    def _fetch_http(self, uri: str, *, timeout: float) -> str:
        # "Accept: */*" is what a plain HTTP client sends; several real
        # competition hosts answer a narrow HTML-only Accept with a bot
        # interstitial instead of the page.
        request = Request(
            uri,
            headers={
                "User-Agent": "Joust/0.1 (+safe-research)",
                "Accept": "*/*",
                "Accept-Language": "en",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200) or 200
                content_length = int(response.headers.get("Content-Length", "0") or 0)
                if content_length > MAX_SOURCE_BYTES:
                    raise SourceTooLarge(uri)
                body = response.read(MAX_SOURCE_BYTES + 1)
                charset = response.headers.get_content_charset() or "utf-8"
        except HTTPError as error:  # 4xx/5xx reached us, but carry no rules
            raise SourceUnreadable(uri, "http_status", f"HTTP {error.code}") from error
        except URLError as error:
            raise SourceUnreadable(uri, "unreachable", str(error.reason)) from error
        if len(body) > MAX_SOURCE_BYTES:
            raise SourceTooLarge(uri)
        if status != 200:
            raise SourceUnreadable(uri, "http_status", f"HTTP {status}")
        text = body.decode(charset, errors="replace")
        if not text.strip():
            raise SourceUnreadable(uri, "empty_body", f"HTTP {status} with no body")
        marker = _challenge_reason(text)
        if marker is not None:
            raise SourceUnreadable(uri, "bot_challenge", f"interstitial matched {marker!r}")
        return text


class _SemanticHTMLParser(HTMLParser):
    def __init__(self, uri: str, authority: str, source_type: str):
        super().__init__(convert_charrefs=True)
        self.result = ParsedSource(uri=uri, authority=authority, source_type=source_type)
        self._capture: tuple[str, dict[str, str]] | None = None
        self._buffer: list[str] = []
        self._text: list[str] = []
        self._block_tag: str | None = None
        self._block_buffer: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_buffer: list[str] = []
        self._ignored_depth = 0

    def _resolve_link(self, href: str) -> str:
        base = urlparse(self.result.uri)
        if Path(self.result.uri).is_absolute() or base.scheme == "":
            return str((Path(self.result.uri).parent / href).resolve())
        return urljoin(self.result.uri, href)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        values = {key: value or "" for key, value in attrs}
        if tag == "body":
            self.result.title = values.get("data-hackathon-name", self.result.title)
            self.result.organizer = values.get("data-organizer") or self.result.organizer
            self.result.deadline = values.get("data-deadline") or self.result.deadline
            self.result.judging_mode = values.get("data-judging-mode") or self.result.judging_mode
        if tag in {"li", "p", "h1", "title"} and self._block_tag is None:
            self._block_tag = tag
            self._block_buffer = []
        if tag in {"li", "p", "section"} and "data-rule" in values:
            self._capture = ("rule", values)
            self._buffer = []
        elif tag in {"li", "p", "section"} and "data-claim-id" in values:
            self._capture = ("claim", values)
            self._buffer = []
        if tag == "a" and values.get("href") and values.get("data-source-authority"):
            linked_uri = self._resolve_link(values["href"])
            self.result.links.append(
                SourceLink(
                    uri=linked_uri,
                    authority=values["data-source-authority"],
                    source_type=values.get("data-source-type", "web"),
                )
            )
        elif tag == "a" and values.get("href"):
            self._anchor_href = values["href"]
            self._anchor_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if self._capture and tag in {"li", "p", "section"}:
            kind, values = self._capture
            text = " ".join(" ".join(self._buffer).split())
            if kind == "rule":
                self.result.rules.append(
                    {
                        "id": values.get("data-rule-id", f"rule-{len(self.result.rules) + 1}"),
                        "kind": values["data-rule"],
                        "text": text,
                    }
                )
            else:
                self.result.claims.append({"id": values["data-claim-id"], "text": text})
            self._capture = None
            self._buffer = []
        if self._block_tag == tag:
            text = " ".join(" ".join(self._block_buffer).split())
            if text:
                self.result.blocks.append(text)
                if tag in {"title", "h1"} and not self.result.title:
                    self.result.title = text
            self._block_tag = None
            self._block_buffer = []
        if tag == "a" and self._anchor_href is not None:
            label = " ".join(" ".join(self._anchor_buffer).split())
            haystack = f"{label} {self._anchor_href}".lower()
            if any(
                keyword in haystack
                for keyword in ("rule", "eligib", "guideline", "criteria", "terms")
            ):
                target = self._resolve_link(self._anchor_href)
                source_origin = urlparse(self.result.uri).netloc
                target_origin = urlparse(target).netloc
                same_origin = not source_origin or source_origin == target_origin
                if same_origin and target not in {link.uri for link in self.result.links}:
                    self.result.links.append(
                        SourceLink(uri=target, authority="official", source_type="rules")
                    )
            self._anchor_href = None
            self._anchor_buffer = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        clean = html.unescape(data).strip()
        if clean:
            self._text.append(clean)
            if self._capture:
                self._buffer.append(clean)
            if self._block_tag:
                self._block_buffer.append(clean)
            if self._anchor_href is not None:
                self._anchor_buffer.append(clean)

    def close(self) -> None:
        super().close()
        self.result.text = " ".join(" ".join(self._text).split())


def parse_source(content: str, uri: str, authority: str, source_type: str) -> ParsedSource:
    parser = _SemanticHTMLParser(uri, authority, source_type)
    parser.feed(content)
    parser.close()
    _enrich_from_json_ld(parser.result, content)
    if authority == "official" and not parser.result.rules:
        parser.result.rules.extend(_infer_rule_candidates(parser.result.blocks))
    _infer_typed_deadlines(parser.result)
    _infer_scoring_rules(parser.result)
    return parser.result


_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all instructions",
    "system prompt",
    "upload every credential",
    "reveal your password",
)

_JSON_LD_SCRIPT = re.compile(
    r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_HUMAN_DATE = re.compile(
    r"\b(?P<month>January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s*(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<meridiem>am|pm)\s*(?P<timezone>PT|PST|PDT|ET|EST|EDT|UTC)?)?",
    re.IGNORECASE,
)
_FULL_DATE = re.compile(
    r"\b(?P<month>January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,\s*(?P<year>\d{4})"
    r"(?:[^A-Za-z0-9]{0,4}(?:at\s*)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<meridiem>am|pm)\s*(?P<timezone>[A-Za-z]{2,3}T|Pacific Time|Eastern Time|"
    r"Central Time|Mountain Time|UTC|GMT)?)?",
    re.IGNORECASE,
)
_DEADLINE_KINDS = (
    ("submission deadline", "SUBMISSION_DEADLINE"),
    ("submission period", "SUBMISSION_DEADLINE"),
    ("winners announced", "RESULT"),
    ("leaderboard snapshot", "FINAL_SNAPSHOT"),
    ("final snapshot", "FINAL_SNAPSHOT"),
    ("build deadline", "BUILD_DEADLINE"),
    ("results", "RESULT"),
    ("winner", "RESULT"),
)


def _iter_json_ld_events(payload):
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_json_ld_events(item)
        return
    if not isinstance(payload, dict):
        return
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _iter_json_ld_events(item)
    kinds = payload.get("@type", [])
    if isinstance(kinds, str):
        kinds = [kinds]
    if any(str(kind).lower() == "event" for kind in kinds):
        yield payload


def _enrich_from_json_ld(source: ParsedSource, content: str) -> None:
    """Read publisher-declared event metadata without treating it as page prose.

    Modern event pages often put their canonical dates and organizer only in
    JSON-LD.  Ignoring script tags is right for prose extraction, but silently
    discarding this standard metadata made Joust miss real competition dates.
    """

    for match in _JSON_LD_SCRIPT.finditer(content):
        try:
            payload = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        for event in _iter_json_ld_events(payload):
            if not source.title and isinstance(event.get("name"), str):
                source.title = event["name"].strip()
            organizer = event.get("organizer")
            if not source.organizer:
                candidates = organizer if isinstance(organizer, list) else [organizer]
                for candidate in candidates:
                    if isinstance(candidate, dict) and isinstance(candidate.get("name"), str):
                        source.organizer = candidate["name"].strip()
                        break
                    if isinstance(candidate, str) and candidate.strip():
                        source.organizer = candidate.strip()
                        break
            if not source.start_at and isinstance(event.get("startDate"), str):
                source.start_at = event["startDate"]
            if not source.end_at and isinstance(event.get("endDate"), str):
                source.end_at = event["endDate"]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


_NAMED_ZONES = {
    "PT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "PACIFIC TIME": "America/Los_Angeles",
    "ET": "America/New_York",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "EASTERN TIME": "America/New_York",
    "CT": "America/Chicago",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "CENTRAL TIME": "America/Chicago",
    "MT": "America/Denver",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "MOUNTAIN TIME": "America/Denver",
}


def _timezone_for_label(label: str | None, fallback: datetime | None):
    if label:
        normalized = " ".join(label.upper().split())
        if normalized in {"UTC", "GMT"}:
            return UTC
        if normalized in _NAMED_ZONES:
            return ZoneInfo(_NAMED_ZONES[normalized])
    return fallback.tzinfo if fallback and fallback.tzinfo else UTC


def _to_24_hour(hour: int, meridiem: str) -> int:
    if hour == 12:
        hour = 0
    return hour + 12 if meridiem.lower() == "pm" else hour


def _infer_full_dates(source: ParsedSource) -> None:
    """Read deadlines that the page states in full, year included.

    Most hackathon hosts publish "Submission Period: ... – Monday, September
    14, 2026 (5:00 pm Pacific Time)" in prose and nowhere else.  These need no
    JSON-LD reference year, and the closing date of a stated period is the
    deadline, so the last full date in the labelled block is the one taken.
    """

    for block in source.blocks:
        normalized = " ".join(block.split())
        lower = normalized.lower()
        deadline_type = next((kind for marker, kind in _DEADLINE_KINDS if marker in lower), None)
        if deadline_type is None or deadline_type in source.deadlines:
            continue
        matches = list(_FULL_DATE.finditer(normalized))
        if not matches:
            continue
        parts = matches[-1].groupdict()
        source.deadline_claims.setdefault(deadline_type, normalized)
        if not parts["meridiem"]:
            source.uncertainty.append(
                f"{deadline_type} is published without a time: {normalized[:200]}"
            )
            continue
        try:
            value = datetime.strptime(
                f"{parts['month']} {parts['day']} {parts['year']}", "%B %d %Y"
            )
        except ValueError:
            continue
        if not parts["timezone"]:
            source.uncertainty.append(
                f"{deadline_type} is published without a time zone: {normalized[:200]}"
            )
        value = value.replace(
            hour=_to_24_hour(int(parts["hour"] or 0), parts["meridiem"]),
            minute=int(parts["minute"] or 0),
            tzinfo=_timezone_for_label(parts["timezone"], None),
        )
        source.deadlines[deadline_type] = value.isoformat()


def _infer_typed_deadlines(source: ParsedSource) -> None:
    """Extract explicitly labelled deadlines using the event's own year.

    A month/day without a year is ambiguous.  We only resolve it when the
    same official page exposes a dated event via JSON-LD, and retain the label
    (submission versus leaderboard snapshot) instead of collapsing dates.
    """

    _infer_full_dates(source)
    reference = _parse_timestamp(source.start_at) or _parse_timestamp(source.end_at)
    if reference is None:
        source.deadline = source.deadline or (
            source.deadlines.get("SUBMISSION_DEADLINE")
            or source.deadlines.get("FINAL_SNAPSHOT")
            or source.deadlines.get("BUILD_DEADLINE")
        )
        return
    for block in source.blocks:
        normalized = " ".join(block.split())
        lower = normalized.lower()
        deadline_type = next(
            (kind for marker, kind in _DEADLINE_KINDS if marker in lower), None
        )
        if deadline_type is None or deadline_type in source.deadline_claims:
            continue
        match = _HUMAN_DATE.search(normalized)
        if match is None:
            continue
        source.deadline_claims[deadline_type] = normalized
        parts = match.groupdict()
        if not parts["meridiem"]:
            source.uncertainty.append(
                f"{deadline_type} is published without a time: {normalized}"
            )
            continue
        try:
            value = datetime.strptime(
                f"{parts['month']} {parts['day']} {reference.year}", "%B %d %Y"
            )
        except ValueError:
            continue
        value = value.replace(
            hour=_to_24_hour(int(parts["hour"] or 0), parts["meridiem"]),
            minute=int(parts["minute"] or 0),
            tzinfo=_timezone_for_label(parts["timezone"], reference),
        )
        source.deadlines[deadline_type] = value.isoformat()
    if source.deadline is None:
        source.deadline = (
            source.deadlines.get("FINAL_SNAPSHOT")
            or source.deadlines.get("SUBMISSION_DEADLINE")
            or source.end_at
        )


def _infer_scoring_rules(source: ParsedSource) -> None:
    for block in source.blocks:
        normalized = " ".join(block.split())
        lower = normalized.lower()
        if "rank" not in lower or not any(
            marker in lower for marker in ("install", "token usage", "leaderboard")
        ):
            continue
        if normalized not in source.scoring_rules:
            source.scoring_rules.append(normalized)
    if source.scoring_rules:
        source.judging_mode = source.judging_mode or "leaderboard"
        source.leaderboard_model = source.leaderboard_model or source.scoring_rules[0]


def _infer_rule_candidates(blocks: list[str]) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    seen: set[str] = set()
    for block in blocks:
        text = " ".join(block.split())
        lower = text.lower()
        explicit_normative = re.search(
            r"\b(must|must not|required|eligible|eligibility|to rank|do not|may not|prohibited)\b",
            lower,
        )
        first_person_markers = re.findall(r"\b(i|me|my|mine|we|us|our|ours)\b", lower)
        if (
            len(text) < 12
            or len(text) > 800
            or any(marker in lower for marker in _INJECTION_MARKERS)
            or (len(first_person_markers) >= 3 and not explicit_normative)
        ):
            continue
        kind: str | None = None
        if re.search(r"\b(must not|may not|prohibited|forbidden|do not|cannot)\b", lower):
            kind = "prohibited"
        elif "license" in lower or re.search(
            r"\b(eligible|eligibility|minimum age|team size|must be|to rank)\b", lower
        ):
            kind = "eligibility"
        elif re.search(r"\b(must use|required to use|built with|build with)\b", lower) or re.search(
            r"\bcopy\b.*\b(client|service)\b|\breport(?:ing)?\b.*\bleaderboard\b", lower
        ):
            kind = "required-technology"
        elif re.search(
            r"\b(submit|submission|provide|include|publish|upload|register|demo|video|repository|source code)\b",
            lower,
        ):
            kind = "submission"
        if kind and lower not in seen:
            seen.add(lower)
            rules.append(
                {
                    "id": f"heuristic-{kind}-{len(rules) + 1}",
                    "kind": kind,
                    "text": text,
                    "extraction": "heuristic",
                }
            )
    return rules


def discover_sources(uri: str, fetcher: SourceFetcher | None = None) -> list[ParsedSource]:
    fetcher = fetcher or SourceFetcher()
    primary = parse_source(fetcher.fetch(uri), uri, "official", "official_page")
    sources = [primary]
    seen = {uri}
    for link in primary.links[:5]:
        if link.uri in seen:
            continue
        seen.add(link.uri)
        try:
            content = fetcher.fetch(link.uri)
        except SourceUnreadable as error:
            # One unreadable related link must not end the mission, but it must
            # not disappear either: it is carried as declared uncertainty.
            primary.uncertainty.append(
                f"related source could not be read ({error.uri}): {error.reason}"
            )
            continue
        sources.append(parse_source(content, link.uri, link.authority, link.source_type))
    readable_text = sum(len(source.text.strip()) for source in sources)
    if readable_text < MIN_READABLE_TEXT and not any(source.rules for source in sources):
        # A script-rendered shell carries no readable rules.  Saying so is the
        # honest outcome; pretending the competition published nothing is not.
        raise SourceUnreadable(
            uri,
            "no_extractable_text",
            f"{len(sources)} reachable page(s) served {readable_text} characters of visible text",
        )
    return sources


def extract_spec(
    mission_id, sources: list[ParsedSource]
) -> tuple[HackathonSpec, list[Evidence], list[str]]:
    official = [source for source in sources if source.authority == "official"]
    if not official:
        raise ValueError("at least one official source is required")
    primary = official[0]
    official_rules: dict[str, tuple[ParsedSource, dict[str, str]]] = {}
    for source in official:
        for rule in source.rules:
            official_rules[rule["id"]] = (source, rule)
    if len(official_rules) < 3:
        raise ValueError("rules lock requires at least three official rule records")

    evidence: list[Evidence] = []
    evidence_by_rule: dict[str, Evidence] = {}
    for rule_id, (source, rule) in official_rules.items():
        item = Evidence(
            mission_id=mission_id,
            claim=rule["text"],
            source_type=source.source_type,
            source_uri=source.uri,
            excerpt=rule["text"][:500],
            confidence=(
                AUTHORITY_CONFIDENCE["official"] if rule.get("extraction") != "heuristic" else 0.85
            ),
            authority="official",
        )
        evidence.append(item)
        evidence_by_rule[rule_id] = item

    contradictions: list[str] = []
    for source in sources:
        if source.authority == "official":
            continue
        for claim in source.claims:
            if (
                claim["id"] in official_rules
                and claim["text"] != official_rules[claim["id"]][1]["text"]
            ):
                contradictions.append(
                    f"{source.authority} claim {claim['id']} conflicts with official source; official retained"
                )
            evidence.append(
                Evidence(
                    mission_id=mission_id,
                    claim=claim["text"],
                    source_type=source.source_type,
                    source_uri=source.uri,
                    excerpt=claim["text"][:500],
                    confidence=AUTHORITY_CONFIDENCE.get(source.authority, 0.25),
                    authority=source.authority,
                )
            )

    by_kind: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for rule_id, (_, rule) in official_rules.items():
        by_kind.setdefault(rule["kind"], []).append((rule_id, rule))

    def requirements(kind: str) -> list[Requirement]:
        return [
            Requirement(
                id=rule_id,
                text=rule["text"],
                blocking=True,
                evidence_ids=[evidence_by_rule[rule_id].id],
            )
            for rule_id, rule in by_kind.get(kind, [])
        ]

    def first_timestamp(field: str) -> datetime | None:
        for source in official:
            value = getattr(source, field)
            parsed = _parse_timestamp(value)
            if parsed is not None:
                return parsed
        return None

    def first_typed_deadline(kind: str) -> datetime | None:
        for source in official:
            parsed = _parse_timestamp(source.deadlines.get(kind))
            if parsed is not None:
                return parsed
        return None

    build_deadline = first_typed_deadline("BUILD_DEADLINE")
    submission_deadline = first_typed_deadline("SUBMISSION_DEADLINE")
    final_snapshot = first_typed_deadline("FINAL_SNAPSHOT")
    result_at = first_typed_deadline("RESULT")
    fallback_deadline = first_timestamp("deadline")
    terminal_deadline = final_snapshot or submission_deadline or build_deadline or fallback_deadline
    scoring_rules = [
        rule
        for source in official
        for rule in source.scoring_rules
    ]
    leaderboard_model = next(
        (source.leaderboard_model for source in official if source.leaderboard_model), None
    )
    spec = HackathonSpec(
        mission_id=mission_id,
        name=primary.title or "Unnamed hackathon",
        organizer=primary.organizer,
        canonical_url=primary.uri,
        start_at=first_timestamp("start_at"),
        build_deadline_at=build_deadline,
        submission_deadline_at=submission_deadline,
        final_snapshot_at=final_snapshot,
        result_at=result_at,
        deadline_at=terminal_deadline,
        judging_mode=primary.judging_mode or ("leaderboard" if scoring_rules else None),
        leaderboard_model=leaderboard_model,
        scoring_rules=scoring_rules,
        deadline_explicitly_unknown=terminal_deadline is None,
        required_technologies=[rule["text"] for _, rule in by_kind.get("required-technology", [])],
        prohibited_actions=[rule["text"] for _, rule in by_kind.get("prohibited", [])],
        submission_requirements=requirements("submission"),
        eligibility_requirements=requirements("eligibility"),
        rule_sources=[source.uri for source in official],
        uncertainty=[
            finding
            for source in official
            for finding in source.uncertainty
        ],
        rules_locked=True,
        evidence_ids=[item.id for item in evidence if item.authority == "official"],
    )
    return spec, evidence, contradictions


def crosscheck_extraction(
    spec: HackathonSpec,
    evidence: list[Evidence],
    contradictions: list[str],
    sources: list[ParsedSource],
) -> list[str]:
    """A separate deterministic pass over the extracted rule set."""

    findings: list[str] = []
    official_evidence = {item.id: item for item in evidence if item.authority == "official"}
    if len(official_evidence) < 3:
        raise ValueError("rules cross-check requires at least three official evidence records")
    missing = [
        evidence_id for evidence_id in spec.evidence_ids if evidence_id not in official_evidence
    ]
    if missing:
        raise ValueError(f"rules cross-check found missing official evidence: {missing}")
    if not any(source.authority != "official" for source in sources):
        findings.append(
            "No independent non-official source was available for contradiction checks."
        )
    elif not contradictions:
        findings.append("Independent sources were checked and no rule contradiction was found.")
    else:
        findings.extend(contradictions)
    tainted = [
        item.claim
        for item in evidence
        if any(marker in item.claim.lower() for marker in _INJECTION_MARKERS)
    ]
    if tainted:
        raise ValueError("rules cross-check rejected instruction-like source content")
    return findings
