# 0005 — Unraid deploy: Compose Manager stack, manual copy

- **Status:** Accepted
- **Date:** 2026-07-03

## Context

The app is a single container, so an Unraid Community Applications template would be the conventional path. However, the user already runs their other stacks (e.g. bumblebee) via the Unraid **Compose Manager** plugin and has an established, deliberate build workflow they want kept consistent. The user chose Compose Manager + a manual copy step for this project too.

## Decision

- **Deploy via the Unraid Compose Manager plugin**, not a CA template. The stack is a `docker-compose.yml` copied to `/mnt/user/appdata/webnovel-to-epub-scraper-docker/` and brought up with **Compose Manager → Compose Up**.
- **Division of labour:** Claude edits Docker source (Dockerfile, compose, app code) **locally in the project folder only**. The **user** copies the stack to appdata and runs Compose Up / rebuild, then confirms. Claude does not copy to the server or trigger builds without explicit per-task approval.
- **Handoff is explicit:** every change needing a deploy ends with a **▶ YOUR TURN** block (numbered steps, rebuild vs restart vs nothing stated plainly).
- **Compose is invoker-safe:** explicit `image:` pin + a named/external network in the compose file, so image tags and networking are correct regardless of the project name Compose Manager derives. Raw `docker compose up`/`build` from the appdata folder is never recommended (it uses the folder name as the project name → wrong image tags, isolated network).

## Consequences

- **+** Consistent with the user's existing Unraid workflow and their control over what lands on the live server.
- **+** The invoker-safe compose avoids the project-name footgun that previously caused a debugging detour on the bumblebee stack.
- **−** Slightly more manual than a one-click CA install (user performs the copy + Compose Up each deploy). Accepted — it's the user's explicit preference.
- **−** A single container via Compose Manager is marginally more setup than a CA template. Acceptable; a GHCR-published image can later let the compose file simply pull a tag, shrinking the copy step.
- Mirrors the memories [[feedback-docker-build-workflow]] and [[feedback_call_out_user_actions]].
