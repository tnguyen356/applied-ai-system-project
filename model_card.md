# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name  

**Museek 2.0**

## 2. Intended Use  

The recommender gives the user a configurable top-k songs (3 by default) matched on mood, energy, tempo, danceability, and acoustic preference, drawn from a real ~114,000-track Spotify catalog. A user can describe what they want in free text ("something slow and sad"), which an agentic layer (Gemini, or a deterministic keyword fallback) turns into the same structured preferences. The assumption this recommender makes is that a user cares about *how a song feels* — its mood, energy, tempo, and danceability — rather than its exact genre label, since this dataset's genre tags are too fragmented (mostly one-off micro-genres) to match on reliably.

## 3. How the Model Works  

For each song, the model looks at: its mood (derived — see Data below), how energetic it
is, its tempo, its danceability, and how acoustic it sounds. Genre is stored on every song
but is **not** scored — see "A suggestion I accepted" below for why.

For you, the model considers your target mood, how much energy you want right now, a
target tempo and danceability (either can be left unspecified — "no preference" instead of
a silent guess), and whether you tend to like acoustic-sounding music or more
produced/electronic music.

To turn that into a score (`score_song` in `src/recommender.py`), it checks each feature
one at a time and adds points:

- If the song's mood matches your target mood exactly, it adds the largest chunk of
  points (mood is weighted highest).
- Energy, tempo, and danceability each add points based on **closeness**, not an exact
  match — a song closer to your target energy/tempo/danceability earns more of that
  feature's points than one further away, instead of a binary hit-or-miss.
- It gives a smaller bonus if the song's acoustic-ness lines up with whether you said you
  like acoustic or produced/electronic music.

All those points sum into one final score per song. Songs are sorted highest to lowest,
deduped so the same track (the source data repeats some tracks under multiple genre tags)
can't occupy two of the top-k slots, and the top few are returned. Each recommendation
still lists the specific reasons it scored the way it did, so it isn't a black box.

A free-text request (e.g. "something slow and sad") goes through an additional plan step
first — see Section 7.5 — that turns it into this same mood/energy/tempo/danceability/
acoustic shape before scoring runs.

---

## 4. Data  

The catalog is a real Spotify tracks dataset (`data/songs.csv`, ~114,000 rows), with
audio features per track: energy, valence, tempo, danceability, acousticness, plus
`track_name`, `artists`, `track_genre`, and a real Spotify `track_id`.

The dataset has no native mood label, so mood is derived from a 3x3 valence/energy
quadrant lookup (`_infer_mood` in `recommender.py`) into nine labels: euphoric,
triumphant, anxious, happy, focused, moody, romantic, dreamy, melancholic. This is a
cheap, explainable heuristic, not a real emotion classifier — two songs with very
different lyrical content but similar valence/energy land in the same bucket.

`track_genre` is mostly one-off micro-genres (`chicago-house`, `r-n-b`, `hardcore`, etc.)
that rarely exact-match between what a user asks for and what a song is tagged with, so
it's kept as metadata but not scored (see Section 3).

The 114,000 rows contain only ~89,741 *unique* tracks — 16,641 groups of duplicate
`track_id`s (40,900 rows) exist because the same song is repeated under multiple genre
tags. `recommend_songs` dedupes by `spotify_url`/`track_id` so the same song can't fill
more than one of the top-k slots in a single result.

---

## 5. Strengths  

**Mood-and-feature matching generalizes beyond the catalog's own vocabulary.** Real
free-text requests that never use a literal catalog mood word still resolve sensibly —
"i want sleep music" correctly mapped to `mood=dreamy, energy=0.30, tempo=60bpm` and
surfaced a literal sleep-music track.

**The system fails honestly instead of guessing.** A request with no resolvable signal
(e.g. a nonsense string) returns a 0.00 score and "No strong matches found" rather than
silently picking an arbitrary mood — this matters far more at 114,000 rows than it did at
18, where a wrong guess is much easier to hide in.

**Graceful degradation holds up under a real failure, not just in theory.** When the
configured Gemini model was discovered to be failing (503/overloaded) across two days of
production logs, the keyword-fallback parser kept both the CLI and the Streamlit app fully
functional with no crash and no silently wrong output — it just returned less flexible
interpretations until the model was fixed.

---

## 6. Limitations and Bias 

- **Mood is a derived heuristic, not a real emotion signal, and is still exact-matched.**
  Mood comes from a coarse 3x3 valence/energy quadrant lookup (Section 4), so two songs
  with very different lyrical content can land in the same bucket just because their
  valence/energy are numerically close — and mood matching itself is still `mood == mood`:
  a request for "happy" scores zero mood points against a song labeled "euphoric" or
  "playful," even though all three sit in the same emotional neighborhood by construction.
- **Dropping genre removes a signal users actually ask for.** Replacing exact genre
  matching with tempo/danceability closeness fixed the one-off-micro-genre problem
  (Section 3), but it also means the system has no way to honor a literal "give me pop"
  request anymore — genre is stored on every song but never scored.
- **Still no diversity or exploration.** The scorer is fully deterministic: the same
  preferences always produce the same top-k, in the same order, every time. At 114,000
  rows there are almost certainly many "good enough" alternatives for a given request, but
  the system always returns the literal highest-scoring set. 
- **The free-text path is only as good as its parser.** Without a working Gemini key (or
  if the configured model is unavailable, as actually happened during this project — see
  Section 9), interpretation falls back to a hand-maintained keyword/regex list. Any
  everyday phrasing that list doesn't anticipate silently resolves to "no preference"
  rather than a weak-but-honest guess, producing a 0.00-scored, effectively arbitrary
  result instead of a near-miss.

## 7. Evaluation  

I evaluate against the 5 profiles in `main.py`'s `PROFILES` dict (`baseline`,
`conflicting_signals`, `diverse_hiphop_anxious`, `diverse_reggae_euphoric`,
`diverse_rnb_romantic`), each specifying mood/energy/tempo/danceability/acoustic — none of
them use genre, since genre isn't scored (Section 3).

For the four "normal" profiles, the top 3 results consistently match on *every* specified
feature at once — mood, energy, tempo, danceability, and acoustic character all hit —
scoring within a tight 0.01-0.1 band of each other, close to the 5.5 theoretical max (e.g.
`baseline`'s top 3 all score 5.38-5.39; `diverse_hiphop_anxious` scores 5.47-5.48). That the
catalog can surface several near-identical, fully-matching candidates for an ordinary
request is reassuring at 114,000 rows, but it's also exactly why Section 6 calls out "no
diversity" as a real limitation: with this many near-ties, always returning the literal
top-k means the same 3 songs every time, with no attempt to sample across the tied pool.

`conflicting_signals` is deliberately contradictory: it asks for a `melancholic` mood —
which, by the valence/energy quadrant that defines it, only exists at low energy — *and* a
target energy of 0.95 with a 170bpm tempo. The scorer doesn't hide this conflict: its top 3
score noticeably lower (4.90, versus 5.31-5.48 for every other profile) and, tellingly,
**none of them earn the "Energy level is close" reason** that every other profile's top
picks get. That's the system being honest about an unresolvable preference instead of
silently picking one signal and ignoring the other.

One more observation from this run: the surfaced tracks span languages the catalog wasn't
filtered for at all — Russian, Mandarin, and Spanish titles all appeared as top matches,
purely because their audio features fit, with no language or lyrical signal involved. That's
a reasonable sign the audio-feature approach generalizes the way it was intended to, though
it's also a reminder that "sounds similar" and "means something similar" aren't the same
claim.

---

## 7.5 Agentic Workflow (Stretch Feature)

To address the exact-match limitation above, `src/agent.py` adds a plan -> act -> check
loop on top of the same deterministic scorer:

- **Plan**: a free-text request (e.g. "something upbeat like pop but I'm open to similar
  genres") is turned into the structured prefs dict `score_song` expects, grounded
  against the catalog's actual genre/mood vocabulary (never invents a label the catalog
  doesn't have) and paired with a ranked list of related fallback genres/moods.
- **Act**: unchanged — `recommend_songs` scores the catalog exactly as before.
- **Check**: if the top score is below a threshold (3.0), the agent retries once using
  the next-closest fallback genre/mood and keeps whichever pass scored higher.

This doesn't remove the exact-match bias from the scorer itself, but it gives the system
a second attempt at a related label (pop -> indie pop) instead of returning a single
rigid miss. When a request mixes conflicting signals (e.g. two different moods), the
planner also returns a one-line `note` explaining which signal it prioritized, so that
choice stays visible rather than silent. If the catalog genuinely lacks what was asked
for (e.g. punk, country - see Data below), the retry still can't invent a song that
isn't there, so the score stays low; this is a known gap rather than something the agent
tries to paper over.

## 8. Future Work  

- **Conversational refinement.** Let a user say "can I get different songs" and have the
  agent reuse the last turn's preferences while excluding already-shown tracks, instead of
  re-parsing that phrase as a brand-new (and unparseable) request.
- **Broaden the retry step.** It currently only swaps in a fallback mood; relaxing
  energy/tempo/danceability too when the first pass is weak would recover more requests
  that miss for a reason other than mood.
- **Diversity beyond literal duplicates.** Deduping by `spotify_url` stops the exact same
  track from filling two slots, but the catalog can still return several very similar
  songs by the same artist — capping results per artist would be the natural next step.

---

## 9. Personal Reflection  

**What I learned about recommender systems:** a recommender is only as honest as the
signals it's allowed to trust. The original toy catalog made exact genre/mood matching
look reasonable because the data was hand-shaped to make it work; the moment the catalog
became a real, messy dataset, the same exact-match logic would have silently failed on
almost everything. The actual engineering work wasn't the scoring formula — it was
deciding which signals were trustworthy enough to score on at all (closeness on audio
features, yes; exact-match on one-off micro-genres, no).

**Something unexpected I discovered:** the most convincing bugs weren't in the model at
all. A hardcoded Gemini model name silently degraded every request to the keyword fallback
for two days without ever throwing a visible error — the system looked fine because the
fallback is designed to be graceful, which is exactly what let a real misconfiguration hide
in plain sight.

**How this changed how I think about these systems:** I now treat "the fallback still
works" and "the tests still pass" as much weaker signals than I used to. Both were true
while the system was recommending the wrong mood, pointing at an overloaded model, and
returning the same song twice — none of which a green test suite caught on its own.

**How I collaborated with AI on this project:** the agent and I worked turn-by-turn —
each feature (Spotify links, deduping, the Streamlit playlist) started with it asking
clarifying questions about scope before writing anything, then verifying the change
against the real 114k-row dataset or a headless run of the app rather than just asserting
it worked. When I spotted somed wrong (a model silently failing, a button that didn't
seem to register), the agent diagnosed it empirically — querying the live API, reproducing
the exact failure — rather than guessing. Every change was reviewed and tested before being
committed, and nothing was pushed without an explicit go-ahead.

**A suggestion I accepted, and one I revised:**
A suggestion I accepted removing genre as a weight due to the new set of data I imported does not include genre. In return, tempo and danceability were used as replacement as genre is just a more rounded way to easy group song with similiar tempo and danceability. One idea I went against AI is "keeping  UserProfile and integrate it into the system". While the idea can be readdress in the future versions of Museek, right now I want to focus on the backbone of this music recommender which is understanding the user's input and turn it into datas to score songs, while introducing some quality of life feature like embing direct link and saved a playlist without disrupting the data handling.