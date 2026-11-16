"""
Agentic workflow layer for the Music Recommender.

Wraps the existing deterministic scorer (recommender.score_song / recommend_songs)
with a plan -> act -> check loop:

  1. Plan  (interpret_request):  free text -> structured prefs + fallback options,
                                  grounded against the real song catalog's vocabulary.
  2. Act   (recommend_songs):    unchanged deterministic scoring.
  3. Check (evaluate_recommendations): decide whether the result is strong enough,
                                  or whether to retry with a fallback genre/mood.

The LLM only ever produces *interpretation*, never scores or picks songs directly -
scoring stays fully deterministic and auditable.
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

try:
    # Running as a script (python src/main.py), src/ is on sys.path directly.
    from recommender import recommend_songs
except ImportError:
    # Imported as a package (e.g. from tests: `from src.agent import ...`).
    from src.recommender import recommend_songs

logger = logging.getLogger("agent")

MIN_ACCEPTABLE_SCORE = 3.0  # below this, we treat the match as weak and retry once
GEMINI_MODEL = "gemini-3.8-flash"

# Used only when energy isn't explicitly stated: a reasonable energy level implied
# by the mood alone (e.g. "happy" reads as more energetic than "melancholic").
# Covers the catalog's actual moods, plus a couple of common synonyms for robustness.
MOOD_ENERGY_DEFAULTS = {
    "intense": 0.9,
    "euphoric": 0.85,
    "triumphant": 0.85,
    "happy": 0.8,
    "playful": 0.7,
    "anxious": 0.65,
    "focused": 0.5,
    "romantic": 0.45,
    "moody": 0.45,
    "nostalgic": 0.4,
    "chill": 0.3,
    "dreamy": 0.3,
    "relaxed": 0.25,
    "melancholic": 0.2,
    "sad": 0.2,
}


def _catalog_vocab(songs: List[Dict]) -> Tuple[List[str], List[str]]:
    """Pulls the live set of genres/moods out of the catalog so the planner
    never invents a label that isn't actually recommendable."""
    genres = sorted({song["genre"] for song in songs})
    moods = sorted({song["mood"] for song in songs})
    return genres, moods


def _keyword_fallback_parse(user_text: str, known_genres: List[str], known_moods: List[str]) -> Dict:
    """Deterministic, no-API parser used when Gemini is unavailable or fails.
    Just substring-matches known catalog vocabulary against the request text."""
    text = user_text.lower()

    matched_genres = sorted((g for g in known_genres if g in text), key=text.index)
    matched_moods = sorted((m for m in known_moods if m in text), key=text.index)

    # None means "not mentioned" - score_song treats that as no preference rather
    # than silently guessing a real genre/mood the user never asked for.
    genre = matched_genres[0] if matched_genres else None
    mood = matched_moods[0] if matched_moods else None

    note = None
    if len(matched_moods) > 1:
        note = (
            f"Request mentioned multiple moods ({', '.join(matched_moods)}); "
            f"picked '{mood}' since it appeared first in your text"
        )

    if re.search(r"\b(intense|high energy|hype|energetic)\b", text):
        energy = 0.9
    elif re.search(r"\b(chill|relax|calm|mellow|low energy)\b", text):
        energy = 0.3
    else:
        # No explicit energy word - fall back to a mood-implied default (e.g. a
        # "happy" request reads as more energetic than a "melancholic" one).
        # Still None (true no-preference) if there's no mood to infer from either.
        energy = MOOD_ENERGY_DEFAULTS.get(mood)

    if re.search(r"\b(acoustic|unplugged|stripped.down)\b", text):
        likes_acoustic = True
    elif re.search(r"\b(produced|electronic sound|synth.heavy)\b", text):
        likes_acoustic = False
    else:
        likes_acoustic = None

    remaining_genres = [g for g in known_genres if g != genre]
    remaining_moods = [m for m in known_moods if m != mood]

    return {
        "genre": genre,
        "mood": mood,
        "energy": energy,
        "likes_acoustic": likes_acoustic,
        "fallback_genres": remaining_genres[:2],
        "fallback_moods": remaining_moods[:2],
        "note": note,
    }


def _validate_and_clean(parsed: Dict, known_genres: List[str], known_moods: List[str]) -> Dict:
    """Guardrail: never let a hallucinated genre/mood or malformed field through
    to the scorer. Anything invalid is dropped and logged."""
    clean = dict(parsed)

    if clean.get("genre") not in known_genres:
        logger.warning("Planner returned unknown genre %r, dropping it", clean.get("genre"))
        clean["genre"] = None

    if clean.get("mood") not in known_moods:
        logger.warning("Planner returned unknown mood %r, dropping it", clean.get("mood"))
        clean["mood"] = None

    try:
        clean["energy"] = max(0.0, min(1.0, float(clean.get("energy", 0.5))))
    except (TypeError, ValueError):
        logger.warning("Planner returned invalid energy %r, defaulting to 0.5", clean.get("energy"))
        clean["energy"] = 0.5

    clean["likes_acoustic"] = bool(clean.get("likes_acoustic", False))

    clean["fallback_genres"] = [g for g in clean.get("fallback_genres", []) if g in known_genres]
    clean["fallback_moods"] = [m for m in clean.get("fallback_moods", []) if m in known_moods]

    note = clean.get("note")
    clean["note"] = note.strip() if isinstance(note, str) and note.strip() else None

    return clean


def interpret_request(user_text: str, songs: List[Dict], client=None) -> Dict:
    """Plan step: turn free text into structured prefs, grounded in the catalog's
    actual genre/mood vocabulary. Falls back to a keyword parser if Gemini is
    unavailable or returns something unusable."""
    known_genres, known_moods = _catalog_vocab(songs)

    if client is None:
        logger.info("No Gemini client configured; using keyword fallback parser for request: %r", user_text)
        return _keyword_fallback_parse(user_text, known_genres, known_moods)

    prompt = f"""A user wants music recommendations. Translate their request into JSON.
Pick values ONLY from these lists - never invent new ones:
  genres: {known_genres}
  moods: {known_moods}

Return JSON matching exactly this shape:
{{
  "genre": "<one value from genres>",
  "mood": "<one value from moods>",
  "energy": <float 0.0-1.0; prefer an explicit energy word like 'chill' or 'intense' if
             present, otherwise infer a reasonable level from the overall mood (e.g.
             happy/euphoric/triumphant/intense ~ 0.8-0.9, playful/anxious ~ 0.65-0.7,
             moody/romantic/focused ~ 0.45-0.5, nostalgic/chill/dreamy ~ 0.3-0.4,
             relaxed/melancholic ~ 0.2-0.3)>,
  "likes_acoustic": <true/false, inferred from words like 'unplugged' vs 'produced'>,
  "fallback_genres": ["<related genres from the list above, closest first>"],
  "fallback_moods": ["<related moods from the list above, closest first>"],
  "note": "<null, UNLESS the request mixed conflicting signals (e.g. two different
            moods, or a genre/mood combo that's in tension) - in that case, one short
            sentence explaining which signal you prioritized and why>"
}}

User request: "{user_text}"
"""
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        parsed = json.loads(response.text)
    except Exception as exc:
        logger.warning(
            "Gemini plan step failed (%s: %s); falling back to keyword parser", type(exc).__name__, exc
        )
        return _keyword_fallback_parse(user_text, known_genres, known_moods)

    cleaned = _validate_and_clean(parsed, known_genres, known_moods)

    if cleaned["genre"] is None or cleaned["mood"] is None:
        logger.warning(
            "Planner output missing required fields after validation; falling back to keyword parser"
        )
        return _keyword_fallback_parse(user_text, known_genres, known_moods)

    logger.info("Plan step parsed request %r -> %s", user_text, cleaned)
    return cleaned


def evaluate_recommendations(recommendations: List[Tuple[Dict, float, str]]) -> Dict:
    """Check step: decide if the top result is a strong enough match."""
    if not recommendations:
        return {"good_enough": False, "reason": "No recommendations returned"}

    top_score = recommendations[0][1]
    good_enough = top_score >= MIN_ACCEPTABLE_SCORE

    reason = (
        f"Top score {top_score:.2f} meets the {MIN_ACCEPTABLE_SCORE} threshold"
        if good_enough
        else f"Top score {top_score:.2f} is below the {MIN_ACCEPTABLE_SCORE} threshold"
    )
    return {"good_enough": good_enough, "reason": reason, "top_score": top_score}


def agentic_recommend(
    user_text: str,
    songs: List[Dict],
    k: int = 3,
    client=None,
) -> Tuple[List[Tuple[Dict, float, str]], List[Dict]]:
    """Runs the full plan -> act -> check (-> retry) loop.

    Returns (recommendations, trace) where trace is a list of step dicts
    suitable for logging/printing so the agent's decisions stay visible.
    """
    trace: List[Dict] = []

    prefs = interpret_request(user_text, songs, client=client)
    trace.append({"step": "plan", "prefs": prefs, "note": prefs.get("note")})

    recommendations = recommend_songs(prefs, songs, k=k)
    check = evaluate_recommendations(recommendations)
    trace.append({"step": "act", "prefs_used": dict(prefs), "top_score": check.get("top_score")})
    trace.append({"step": "check", **check})

    if not check["good_enough"]:
        fallback_genres = prefs.get("fallback_genres") or []
        fallback_moods = prefs.get("fallback_moods") or []

        if fallback_genres or fallback_moods:
            retry_prefs = dict(prefs)
            if fallback_genres:
                retry_prefs["genre"] = fallback_genres[0]
            if fallback_moods:
                retry_prefs["mood"] = fallback_moods[0]

            retry_recommendations = recommend_songs(retry_prefs, songs, k=k)
            retry_check = evaluate_recommendations(retry_recommendations)
            trace.append(
                {
                    "step": "retry",
                    "prefs_used": retry_prefs,
                    "top_score": retry_check.get("top_score"),
                }
            )

            if retry_check.get("top_score", 0) > check.get("top_score", 0):
                logger.info("Retry improved top score (%.2f -> %.2f); using retry results",
                            check.get("top_score", 0), retry_check.get("top_score", 0))
                recommendations = retry_recommendations
            else:
                logger.info("Retry did not improve on first pass; keeping original results")

    return recommendations, trace


GEMINI_TIMEOUT_MS = 20_000  # cap how long we wait before falling back to the keyword parser


def build_gemini_client():
    """Returns a configured Gemini client, or None if no API key is set."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set; agent will use the keyword fallback parser")
        return None

    from google import genai
    from google.genai import types

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
