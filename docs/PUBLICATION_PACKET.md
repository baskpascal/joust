# Agent Index publication packet

This file records the public metadata and publication evidence for the released
Agent Index entry.

## Current entry

- Agent id: `galahad-hackathon`
- Public name: Galahad
- Runtime: Hermes / Plow
- Page: <https://aiworthusing.com/agent-index/galahad-hackathon>
- Community listing: live
- Usage reporting: live
- Verified: unavailable until 2026-09-14
- Public repository: `https://github.com/baskpascal/galahad`
- Default branch: `main`
- Description: `Evidence-first Hermes agent that helps teams research, build, red-team, and package hackathon entries.`
- Topics: `ai-agent`, `hackathon`, `hermes`, `plow`, `python`
- Validated local source bundle: `dist/galahad-public.zip`
- Install URL: `https://github.com/baskpascal/galahad#readme`
- One-click install URL: pending Plow-team setup
- Demo media: pending

## Prepared use case 1

- Story id: `live-source-safety`
- Title: `Turned a live hackathon page into a safe, evidence-backed mission`
- Tag: `Engineering`
- Body:

  Lucas asked Galahad to analyze the live Agent Index page. It fetched the
  official source, extracted six evidence records, rejected narrative user
  stories as rule evidence, and stopped safely when the page did not state a
  critical prohibition. The mission remained persisted in `BLOCKED` with the
  exact quality finding and no downstream work marked ready. That rehearsal
  exposed and led to fixes in live HTML extraction, container package
  permissions, and runtime diagnostics. The rebuilt agent passed 74 tests, its
  live doctor returned healthy, and its supervised usage report returned HTTP
  200.

## Publication command shape

The repository, metadata, install URL, and story were published on 2026-09-12.
The rendered public page confirmed the GitHub install link and the Engineering
use case. Do not place the Plow credential or Agent Index key in source or
publication commands.

## Remaining public assets

1. Ask the Plow team for the one-click deployment URL when that program opens.
2. Capture a real mission walkthrough and add screenshots or a short demo.
3. Request Verified from the public agent page on or after 2026-09-14.
