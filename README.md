# 🎵 Music Recommender Simulation — Applied AI System

## Original Project (Modules 1–3)

This project builds on **Museek 1.0**, the "Music Recommender Simulation" built in
Modules 1–3. That original version represented each of 18 hand-authored songs as a
dictionary of attributes (genre, mood, energy, acousticness) and a listener as a simple
preference dictionary (favorite genre, favorite mood, target energy, acoustic preference).
It scored every song with a weighted, exact-match rule — matching genre and mood counted
most, energy closeness was a smaller tiebreaker — and returned the top 3 songs along with
a plain-language explanation of why each one scored the way it did.

## Summary

This phase takes that same deterministic scorer and makes it work against a real,
~114,000-track Spotify dataset instead of a hand-written toy catalog, and wraps it in an
agentic layer that turns a free-text request ("something slow and sad") into the
structured preferences the scorer expects. Two design problems came with the real
dataset: it has no `mood` label at all, and its genre values are mostly one-off
micro-genres that almost never exact-match between what a user asks for and what a song
is tagged with. The project solves both by deriving mood from audio features
(valence/energy) and by replacing exact genre matching with closeness on audio features
(tempo, danceability) instead. It matters because it's the difference between a
classroom toy that only works on data shaped exactly like its examples, and a system that
can be pointed at a real, messy dataset and still produce sensible, explained
recommendations.

---

## Architecture Overview

A Mermaid version of this diagram (same components, rendered on GitHub) lives at
[`diagrams/system_architecture.md`](diagrams/system_architecture.md), with the raw
source at [`diagrams/system_architecture.mmd`](diagrams/system_architecture.mmd).

```
┌───────────────────────────┐
│  data/songs.csv            │   ~114,000 Spotify tracks
│  (track_name, artists,      │   (no "mood" column; genre is
│   track_genre, tempo,       │    mostly one-off micro-genres)
│   danceability, valence,    │
│   energy, acousticness...)  │
└─────────────┬───────────────┘
              │ load_songs()  — recommender.py
              │   - renames columns to this project's schema
              │   - derives "mood" from a valence/energy quadrant lookup
              ▼
┌───────────────────────────────────┐
│  Song dicts: title, artist, genre, │
│  mood, energy, tempo_bpm, valence, │
│  danceability, acousticness,       │
│  spotify_url                       │
└─────────────┬──────────────────────┘
              │
   ┌──────────┴───────────────────────────────┐
   │ (A) Static profile path                    │ (B) Agentic chat path (--chat or app.py)
   ▼                                            ▼
┌───────────────────────┐          ┌─────────────────────────────────┐
│ PROFILES dict (main.py)│          │ Free-text request, e.g. "chill"  │
│ mood/energy/tempo/      │          └────────────────┬──────────────────┘
│ danceability/acoustic   │                           │ interpret_request()  — agent.py
└───────────┬─────────────┘                           │   PLAN: Gemini (if GEMINI_API_KEY
            │                                          │   is set) or a deterministic keyword
            │                                          │   fallback parser turns text into the
            │                                          │   same prefs shape, grounded against
            │                                          │   the catalog's real mood vocabulary
            │                                          ▼
            │                             ┌─────────────────────────────┐
            │                             │ structured prefs dict         │
            │                             │ mood/energy/tempo/danceability │
            │                             │ /acoustic + fallback moods      │
            │                             └────────────────┬────────────────┘
            └─────────────────────┬────────────────────────┘
                                  ▼
                   ┌───────────────────────────────┐
                   │ score_song / recommend_songs    │  ACT — recommender.py
                   │ weighted closeness scoring:      │
                   │ mood match, energy/tempo/         │
                   │ danceability closeness, acoustic, │
                   │ deduped by spotify_url/id          │
                   └────────────────┬──────────────────┘
                                    │
                           (agentic path only)
                                    ▼
                   ┌───────────────────────────────┐
                   │ evaluate_recommendations()       │  CHECK — agent.py
                   │ top score strong enough?          │
                   │ no -> retry once with the next     │
                   │ fallback mood, keep the better pass │
                   └────────────────┬──────────────────┘
                                    ▼
              Top-k ranked, deduped songs + plain-language match
                      reasons + Spotify links to each track
                                    │
                         (Streamlit UI only)
                                    ▼
                   ┌───────────────────────────────┐
                   │ Playlist (browser session state) │  app.py
                   │ per-song Add/Remove, persists      │
                   │ across every query in the session  │
                   └───────────────────────────────┘
```

`src/main.py` is the entry point for both static/CLI paths: with no flags it runs the
fixed `PROFILES` through the static path; `--chat` drives the agentic loop interactively
and prints the plan/act/check/retry trace alongside the recommendations. `app.py`
(`streamlit run app.py`) drives the same agentic loop through a browser chat UI instead of
the terminal, and additionally lets the user save recommendations into a playlist that
persists across queries for the session.

---

## Setup Instructions

1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac or Linux
   .venv\Scripts\activate         # Windows
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the static-profile demo:

   ```bash
   python src/main.py
   ```

4. (Optional) Enable the Gemini-backed planner for the agentic mode. Copy
   `.env.example` to `.env` and fill in your key:

   ```bash
   cp .env.example .env
   ```

   Without a key, the agent automatically falls back to a deterministic keyword
   parser — the app still runs, just with less flexible language understanding.

5. Run the interactive agentic chat mode:

   ```bash
   python src/main.py --chat
   ```

   Type a free-text request (e.g. `something chill`) and the agent prints its
   plan/act/check trace alongside the recommendations. Press Enter on a blank line to
   quit.

   Logs for every plan/act/check/retry decision are written to `logs/agent.log` (and
   printed to the console).

6. Run the Streamlit chat UI (`app.py`, project root):

   ```bash
   streamlit run app.py
   ```

   Same agentic plan/act/check/retry loop as `--chat`, in a browser chat window instead
   of the terminal. The sidebar shows catalog size, whether the Gemini planner or the
   keyword fallback is active, the live catalog mood vocabulary, and a slider for how
   many recommendations to return; each assistant reply has a collapsible trace panel.

7. Run the test suite:

   ```bash
   pytest
   ```

   `tests/test_agent.py` tests the agent's parsing, validation, mood inference, and
   retry logic against a small in-memory catalog with no network calls, so it stays
   reproducible offline.

---

## Sample Interactions

**1. Static profile (`python src/main.py`, `baseline` profile)**

```
Profile: baseline -> {'mood': 'happy', 'energy': 0.8, 'tempo_bpm': 120.0, 'danceability': 0.75, 'likes_acoustic': False}

1. Crimewave by Crystal Castles
   Score: 5.39
   Reasons:
     - Matches your favorite mood (happy)
     - Energy level is close to what you're looking for
     - Tempo is close to what you're looking for
     - Danceability is close to what you're looking for
     - Has a produced, non-acoustic sound matching your taste
```

**2. Agentic chat, free-text request: `chill`**

The word "chill" sets a low energy target but isn't itself one of the catalog's derived
mood labels. The planner maps it to the closest real mood (`dreamy`) instead of leaving
the mood unset:

```
[plan]  mood=dreamy energy=0.30 tempo=unspecified danceability=unspecified acoustic=unspecified
[act]   top score 3.00
[check] ok - Top score 3.00 meets the 3.0 threshold

1. A Sunday Kind Of Love by Etta James
   Score: 3.00
   Reasons:
     - Matches your favorite mood (dreamy)
     - Energy level is close to what you're looking for
```

**3. Agentic chat, nonsense request: `xyzzy nonsense request`**

When nothing in the request maps to a known mood or feature, the system reports that
honestly instead of guessing:

```
[plan]  mood=unspecified energy=unspecified tempo=unspecified danceability=unspecified acoustic=unspecified
[act]   top score 0.00
[check] weak - Top score 0.00 is below the 3.0 threshold

1. Comedy by Gen Hoshino
   Score: 0.00
   Reasons:
     - No strong matches found
```

---

## Design Decisions

- **Real dataset over toy catalog.** Swapping in a ~114,000-track Spotify dataset
  makes the project meaningfully harder but far more credible as a portfolio piece — it
  forces the code to handle a schema it wasn't written for, rather than one tailored to
  make the scorer look good. The trade-off is that `load_songs` now does real column
  mapping instead of a trivial 1:1 read.
- **Derived mood instead of a given label.** The dataset has no mood column, so mood is
  derived from a 3×3 valence/energy quadrant (`_infer_mood` in `recommender.py`), reusing
  label names the agent's energy-inference table already understood. This is a cheap,
  explainable heuristic, not a real emotion classifier — two songs with very different
  lyrical content but similar valence/energy land in the same bucket.
- **Audio-feature closeness instead of exact genre match.** At this dataset's scale,
  genre is mostly one-off micro-genres (and some genre values are themselves mood words
  like `"happy"`), so exact-match genre scoring would almost never fire. Scoring
  closeness on tempo and danceability instead captures "sounds similar" more robustly.
  The trade-off: a human-readable reason like "matches your favorite genre (pop)" is gone,
  replaced by feature-level reasons like "tempo is close to what you're looking for."
- **Deterministic keyword fallback alongside an optional LLM planner.** The agent's plan
  step can use Gemini, but always has a regex-based fallback so the app and test suite
  run fully offline and reproducibly without an API key. The cost is that the fallback's
  vocabulary is necessarily limited by hand — it initially missed everyday words like
  "chill" entirely (see Testing Summary), which an LLM would have handled more gracefully.
- **Single-step mood-only retry.** The check step retries once, swapping in the next
  related mood, rather than searching over every combination of mood/energy/tempo. This
  keeps the control flow easy to reason about and test, at the cost of still returning a
  weak match if the catalog genuinely lacks a related mood for the request.

---

## Testing Summary

**Automated:** 10 tests in `tests/test_agent.py` cover keyword-fallback mood/energy/tempo/
danceability inference, mood-synonym mapping, field validation and clamping, and the
retry loop — all against a tiny in-memory catalog so they run offline, deterministically,
and fast (`pytest`, 10 passed).

**What worked:** the deterministic scorer and the plan→act→check loop carried over
cleanly once `load_songs` learned the new schema; the keyword fallback parser's structure
(regex per feature, `None` means "no stated preference") scaled well to adding tempo and
danceability inference alongside the existing energy/acoustic logic.

**What didn't work at first, and what I learned:**
- The very first run against the new CSV crashed immediately (`KeyError: tempo_bpm`) —
  a reminder that "the code runs on my test data" says nothing about whether it runs on
  *different* data with the same intended shape.
- A Windows console encoding crash appears partway through the static-profile demo when
  an artist name contains a character outside `cp1252`. This is a terminal/display issue,
  not a scoring bug, so it's documented here rather than silently patched over.
- The most interesting bug — asking for "chill" music and getting back an anxious song —
  passed every unit test, because the test fixtures used a tiny 2-mood catalog that never
  exercised the full mood vocabulary or the "mood never resolved" fallback path. It only
  surfaced by manually running the real `--chat` mode with ordinary language. That's the
  main lesson from this phase: tests built around a small, clean fixture can all pass
  while the system still clearly misbehaves on realistic input, so manual, exploratory
  testing against the real data is not optional.

---

## Reflection

Swapping in a real dataset made clear how much the original project's "working" code was
quietly coupled to its toy data's exact shape — a handful of clean column names, a
hand-authored mood label, a short genre list. Making it actually work wasn't just a
column-renaming exercise; it meant rethinking which signals the system could even trust
once genre stopped being usable as an exact-match feature and mood had to be inferred
rather than handed to it. The most convincing bug of this phase (a "chill" request
surfacing an anxious song) didn't come from the LLM at all — it came from a perfectly
reasonable-looking piece of deterministic glue code whose one hidden assumption quietly
broke. That was a good reminder that in an AI-adjacent system, the plain Python stitching
everything together deserves exactly as much scrutiny as the model it's wrapped around.

For the graded responsible-AI reflection — how I collaborated with AI, a suggestion I
accepted and one I revised, and this system's limitations — see
[`model_card.md`](model_card.md).
