# Agent Index publication packet

This file prepares public metadata without performing the external publication
step. Publishing a story, repository, image, video, or install URL requires the
owner's explicit confirmation.

## Current entry

- Agent id: `galahad-hackathon`
- Public name: Galahad
- Runtime: Hermes / Plow
- Page: <https://aiworthusing.com/agent-index/galahad-hackathon>
- Community listing: live
- Usage reporting: live
- Verified: unavailable until 2026-09-14
- Proposed public repository: `https://github.com/baskpascal/galahad`
- Proposed default branch: `main`
- Proposed description: `Evidence-first Hermes agent that helps teams research, build, red-team, and package hackathon entries.`
- Proposed topics: `ai-agent`, `hackathon`, `hermes`, `plow`, `python`
- Validated local source bundle: `dist/galahad-public.zip`
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
  permissions, and runtime diagnostics. The rebuilt agent passed 71 tests, its
  live doctor returned healthy, and its supervised usage report returned HTTP
  200.

## Publication command shape

Use the pinned client with `--agent galahad-hackathon`,
`--story live-source-safety`, the title and body above, and
`--tag Engineering`. Do not place the Plow credential or Agent Index key in the
command; the client uses the existing private registration state.

## Remaining public assets

1. Create the public `baskpascal/galahad` repository and push the current HEAD
   to `main` (the target does not exist as of 2026-09-12).
2. Ask the Plow team for the one-click deployment URL when that program opens.
3. Add the resulting repository and install URLs to the public entry.
4. Capture a real mission walkthrough and add screenshots or a short demo.
5. Request Verified from the public agent page on or after 2026-09-14.
