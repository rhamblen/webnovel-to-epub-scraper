# 0004 — Legal & ethical use policy

- **Status:** Accepted
- **Date:** 2026-07-03

## Context

Scraping tools can be misused. This project is a personal-use utility for reading novels on one's own device. It should encode responsible behavior by design, not leave it to the user's goodwill.

## Decision

- **Personal use only.** The tool is for individuals assembling content they are permitted to read, for their own device. This is stated plainly in the README.
- **Polite by construction.** Rate limiting, per-host concurrency caps, exponential backoff, an honest User-Agent, and `robots.txt` respect live in the shared fetch layer — inherited by every adapter and not trivially disabled.
- **No paywalled or authenticated sources.** The tool does not implement login, paywall bypass, DRM removal, or credential handling. Such sources are out of scope.
- **No redistribution features.** Output goes to the user's own file share; there is no public sharing/hosting feature.

## Consequences

- **+** The tool's default behavior is defensible and considerate of source sites.
- **+** Clear scope boundary keeps the project out of DRM/paywall-circumvention territory.
- **−** Some content (paywalled/login-gated) is deliberately unsupported. Accepted — it is outside the tool's purpose.
- **Note:** users remain responsible for complying with the terms of service and copyright law applicable to the sites and content they access.
