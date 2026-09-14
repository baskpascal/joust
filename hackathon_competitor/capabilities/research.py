from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

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
    judging_mode: str | None = None
    rules: list[dict[str, str]] = field(default_factory=list)
    claims: list[dict[str, str]] = field(default_factory=list)
    links: list[SourceLink] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    text: str = ""


class SourceTooLarge(ValueError):
    pass


class SourceFetcher:
    def fetch(self, uri: str, *, timeout: float = 20.0) -> str:
        local_candidate = Path(uri)
        if local_candidate.is_absolute():
            if local_candidate.stat().st_size > MAX_SOURCE_BYTES:
                raise SourceTooLarge(f"source exceeds {MAX_SOURCE_BYTES} bytes")
            return local_candidate.read_text(encoding="utf-8")
        parsed = urlparse(uri)
        if parsed.scheme in {"http", "https"}:
            request = Request(uri, headers={"User-Agent": "Joust/0.1 (+safe-research)"})
            with urlopen(request, timeout=timeout) as response:
                content_length = int(response.headers.get("Content-Length", "0") or 0)
                if content_length > MAX_SOURCE_BYTES:
                    raise SourceTooLarge(f"source exceeds {MAX_SOURCE_BYTES} bytes")
                body = response.read(MAX_SOURCE_BYTES + 1)
                if len(body) > MAX_SOURCE_BYTES:
                    raise SourceTooLarge(f"source exceeds {MAX_SOURCE_BYTES} bytes")
                charset = response.headers.get_content_charset() or "utf-8"
                return body.decode(charset, errors="replace")
        if parsed.scheme == "file":
            path = Path(parsed.path)
        elif parsed.scheme == "":
            path = Path(uri)
        else:
            raise ValueError(f"unsupported source scheme: {parsed.scheme}")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise SourceTooLarge(f"source exceeds {MAX_SOURCE_BYTES} bytes")
        return path.read_text(encoding="utf-8")


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
    if authority == "official" and not parser.result.rules:
        parser.result.rules.extend(_infer_rule_candidates(parser.result.blocks))
    return parser.result


_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all instructions",
    "system prompt",
    "upload every credential",
    "reveal your password",
)


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
        sources.append(
            parse_source(fetcher.fetch(link.uri), link.uri, link.authority, link.source_type)
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

    deadline = datetime.fromisoformat(primary.deadline) if primary.deadline else None
    spec = HackathonSpec(
        mission_id=mission_id,
        name=primary.title or "Unnamed hackathon",
        organizer=primary.organizer,
        canonical_url=primary.uri,
        deadline_at=deadline,
        judging_mode=primary.judging_mode,
        deadline_explicitly_unknown=primary.deadline is None,
        required_technologies=[rule["text"] for _, rule in by_kind.get("required-technology", [])],
        prohibited_actions=[rule["text"] for _, rule in by_kind.get("prohibited", [])],
        submission_requirements=requirements("submission"),
        eligibility_requirements=requirements("eligibility"),
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
