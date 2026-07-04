# Phase 7 spec — Content cleaning (v1.1.0)

**Status:** ◐ in progress — Layers 0+2 shipped (2026-07-04) as a countable, opt-in pass; this
doc is still the forward spec for the rest (Layer 1 dedup, Layer 3/4 AI). See "Shipped so far"
below for what actually landed and where it deviates from the original design.

## Shipped so far (2026-07-04)

- **`core/clean.py`** gained `apply_standard_cleanup()` (+ `_GENERIC_JUNK_PATTERNS`,
  `_spaced_token_pattern`, `_scrub`): a labeled, countable second pass over already-cleaned
  `<p>` markup. Catches spacing/punctuated obfuscation of a book's own site name (via new
  `Adapter.site_terms` on each adapter) plus the existing generic junk phrases, now labeled
  (e.g. "Site name", "Translator credit") and tallied instead of silently dropped. Layer 0
  (`clean_chapter_html` / `_JUNK_SUBSTRINGS`) is untouched.
- **New `core/reclean.py`** (`clean_volume`) re-derives `Chapter.clean_html` for a volume's
  chapter range and persists an aggregate report onto two new nullable `Volume` columns:
  `clean_report` (JSON label→count) and `clean_report_at`.
- **Trigger — deviates from the "manual re-clean only" decision below:** ships as a dedicated
  **"Clean" / "Re-clean" button next to Build/Rebuild** (`novel.html` + `build_volume_route`
  in `routes/pages.py`, wired through `build.build_volume(..., do_clean=)`), not a separate
  standalone "Re-clean book" action. A live user request asked specifically for a rebuild-time
  option with a visible counts box — first built as a checkbox on the build form, then changed
  to its own button per follow-up feedback, since a separate button reads more clearly than a
  modifier checkbox — recording the change here rather than leaving the old language looking
  current.
- **Homoglyph folding added (2026-07-04, same day):** a real book (*The Scumbag's Guide To
  Heroism* on freewebnovel.vip) turned out to actively use per-letter Unicode look-alike
  substitution to obfuscate its injected watermark, rotating through Cyrillic/Greek/Latin-
  Extended-B/small-capital lookalikes for 1-3 letters per occurrence (e.g. `frёeωebɳovel.com`,
  `fɾeeweɓnѳveɭ.com`) — confirmed against 10 real variants (5 pulled live, 5 reported by the
  user from a built PDF) plus this doc's own `freewebnᴏvel` example. `_CONFUSABLE_GROUPS` in
  `core/clean.py` folds ~25 Unicode letters per a-z slot (drawn from the families actually
  observed) into the site-name regex, so `apply_standard_cleanup` now catches all of them —
  including obfuscation inside the `.com`-style suffix itself. Verified idempotent and free of
  false positives against genuine accented prose (Chloë, café, façade) and stylized small-caps
  chapter-title text. Not a general Unicode-confusables library (e.g. Unicode's own
  `confusables.txt`) — a curated table scoped to the letter-lookalike families actually seen
  in the wild for this kind of watermark.
- **Not done yet, still applies from the design below:** `Chapter.raw_html` is still
  unpopulated (deferred to precede Layer 1, which actually needs untouched text to count
  paragraph frequency correctly). Layer 1 (frequency dedup) and Layers 3/4 (AI) are entirely
  unbuilt — the rest of this doc below is still the plan for them. (The AI layers were
  considered as the fix for the homoglyph gap above and deliberately not used — this turned
  out to be a bounded, deterministic text-normalization problem, not one needing inference.)

**Goal:** strip two kinds of junk from scraped chapter bodies:
1. **Repeated ad/comment blocks** at the end (or start) of chapters, identical across many chapters.
2. **Injected site-name watermarks**, including mid-sentence and obfuscated forms
   (`f r e e w e b n o v e l`, homoglyphs, `(freewebnᴏvel.com)`).

Today's cleaning is only a static substring blocklist — see `_JUNK_SUBSTRINGS` in
`docker/app/core/clean.py`, applied per-paragraph inside `clean_chapter_html()`.

---

## Current state (facts to build on)

- **Cleaning entry point:** `core/clean.py::clean_chapter_html(container, strip_notes)` — called
  once per chapter from `core/adapters/freewebnovel.py::fetch_chapter()`.
- **Scrape loop:** `core/scrape.py::scrape_bodies()` fetches + cleans pending chapters and stores
  `Chapter.clean_html` + `content_hash`. Idempotent (only fetches chapters lacking `clean_html`).
- **DB:** SQLite (`core/db.py`), single file, single writer. `_ensure_columns()` does safe additive
  `ALTER TABLE ADD COLUMN` migrations on startup — new nullable columns need no DB wipe.
- **Models (`core/models.py`):** `Chapter` **already has a `raw_html` column** (currently unused —
  nothing populates it). `Book` has no pattern store yet.
- **App shape:** server-rendered FastAPI + Jinja/HTMX. Routes = `routes/pages.py` + `routes/health.py`.
  **No JSON API** yet (matters for v2.0, not Phase 7).
- **Deploy:** Claude edits docker source **locally only**; user copies to
  `/mnt/user/appdata/webnovel-to-epub-scraper-docker/` and does **Compose Manager → Compose Up**.
  Never raw `docker compose` CLI. End work with an explicit **▶ YOUR TURN** block.

---

## Design — layered, cheap→expensive, short-circuit early

| Layer | What | AI? | Catches |
|-------|------|-----|---------|
| 0 | current substring blocklist (exists) | no | known exact watermarks |
| 1 | cross-chapter frequency dedup | no | repeated ad/comment blocks |
| 2 | fuzzy / homoglyph site-name scrub | no | most mid-text site-name injections |
| 3 | local-Ollama AI span extraction (via n8n) | yes | novel/obfuscated junk the rules miss |
| 4 | verify-subset guardrail | no | rejects any hallucinated rewrite |

Run 0–2 first (instant, free, deterministic). Only send the *residual* to Layer 3. Always apply
Layer 4 to Layer 3 output.

### Layer 1 — cross-chapter frequency dedup (no AI) — **biggest immediate win**
- New module `core/dedup.py`. Runs as a **post-scrape pass over a whole book** (all bodies already
  in SQLite).
- Normalize each `<p>` (lowercase, collapse whitespace), hash it, count how many chapters in the
  book contain it. Paragraphs present in a high fraction (start ~0.3 threshold), especially the
  first/last 1–2 of a chapter, are boilerplate → drop.
- Near-duplicates (ad with a rotating number/date): catch with shingling or `difflib` ratio.

### Layer 2 — fuzzy site-name scrub (no AI)
- Extend `core/clean.py`: normalize spacing + fold homoglyphs, then regex-remove known site tokens
  and templates (`read latest at …`, `updated on …`). Must remove **fragments** within a paragraph,
  not just drop whole paragraphs.

### Layer 3 — local Ollama on UR1 (GPU), called via **n8n webhook**
- App POSTs mostly-clean chapter text to an n8n webhook; n8n runs the Ollama node and returns
  `{"junk_spans": ["...", "..."]}` (JSON-schema constrained). Model: `qwen2.5:7b-instruct` or
  `llama3.1:8b-instruct`.
- **Prompt rule:** return exact substrings to remove — **never** rewritten/summarized prose.
- n8n owns prompt + model + retries so tuning needs **no Docker rebuild**. App owns the DB; n8n
  never writes it.
- New module `core/ai_clean.py` (HTTP client + response validation). Async — fits the existing
  `scrape_bodies` loop; gate concurrency to 1–2 in flight.

### Layer 4 — verify-subset guardrail (no AI) — **non-negotiable**
- After removing spans, verify every kept sentence still exists **verbatim** in the source. If the
  cleaned text isn't a strict subset of the original, **reject** the AI result and fall back to
  Layers 0–2. Small local models paraphrase/drop text; this catches it.

### Pattern promotion
- AI-found junk spans → stored per book (`Book.boilerplate_patterns`) and re-applied
  deterministically to later chapters, so AI calls taper toward zero.

---

## Concrete work items

1. **Schema**
   - Populate the existing `Chapter.raw_html` in `scrape_bodies` (store the raw body before cleaning
     → enables re-clean without re-fetch).
   - Add `Book.boilerplate_patterns: Optional[str]` (JSON/newline-delimited). `_ensure_columns`
     migrates it automatically.
2. **`core/dedup.py`** — Layer 1 frequency/near-dup pass over a book.
3. **`core/clean.py`** — Layer 2 homoglyph/fuzzy scrub; keep Layer 0.
4. **`core/ai_clean.py`** — Layer 3 Ollama-via-n8n client + Layer 4 subset guardrail + pattern
   promotion.
5. **Settings (`settings_store.py`)** — `ollama_url`, `ollama_model`, `n8n_clean_webhook_url`,
   `ai_clean_enabled` (default off).
6. **Re-clean action** — a route + Novel-page button to reprocess an existing book through the
   layers using stored `raw_html` (no re-fetch). **Manual-trigger only** (see below).
7. **Wire ordering** — chapter clean = Layers 0+2; whole-book pass = Layer 1 + optional Layer 3/4.

### Trigger decision (agreed, still applies to Layer 1/3/4): manual re-clean only
- **Amended for Layers 0+2 (see "Shipped so far" above):** the countable Layers 0+2 pass
  ships as a dedicated per-build "Clean"/"Re-clean" button, not a standalone action — a later,
  more specific user request superseded this section for those two layers only.
- The whole-book cleaning pass (Layer 1 dedup, and later Layer 3/4) runs **only when the user
  clicks "Re-clean book"** — it does **not** auto-run at the end of `scrape_bodies`.
- Rationale: dedup/AI touch every chapter; eyeball the result on a book before trusting the
  thresholds. Auto-running at end of scrape can be added later once thresholds are trusted.
- `scrape_bodies` still stores `raw_html` and does per-chapter Layers 0+2 inline; the whole-book
  frequency pass is deferred to the manual action.

## n8n webhook contract (Layer 3)

```
POST <n8n_clean_webhook_url>
req:  { "text": "<mostly-clean chapter text>", "site": "freewebnovel" }
resp: { "junk_spans": ["<exact substring>", "..."] }   # [] if nothing to remove
```
App then deletes spans, runs the subset guardrail, and on pass stores the result + promotes spans.

## Build order (recommended)

1. Schema (`raw_html` populate + `boilerplate_patterns`) + **Layer 1 dedup** + **Layer 2 scrub** —
   **no Ollama, no n8n.** Verify on a real book (repeated ads + site names gone, no text lost).
2. Then `ai_clean.py` (Layer 3 + 4) behind `ai_clean_enabled`, pointed at the n8n webhook.

## Exit criteria

- On a real multi-chapter book: repeated end-of-chapter ad blocks removed; mid-text site names
  removed; **no story text lost** (subset guardrail holds); re-clean is idempotent.

## Out of scope (→ v2.0)

Moving the whole pipeline into an n8n orchestrator + adding the `/api` surface. See the v2.0 section
in `docs/project-plan.md`.
