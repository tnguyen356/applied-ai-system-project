"""
Command line runner for the Music Recommender Simulation.

This file helps you quickly run and test your recommender.

You will implement the functions in recommender.py:
- load_songs
- score_song
- recommend_songs

It also exposes an agentic mode (src/agent.py) that turns a free-text
request into structured preferences, runs the existing scorer, and
self-checks/retries if the first pass is a weak match.
"""

import logging
import os
import sys

from dotenv import load_dotenv

from agent import agentic_recommend, build_gemini_client
from recommender import load_songs, recommend_songs

# Resolve paths relative to the project root (parent of this file's src/ dir),
# so the app runs correctly regardless of the caller's current working directory.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SONGS_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "songs.csv")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")


PROFILES = {
    "baseline": {"genre": "pop", "mood": "happy", "energy": 0.8, "likes_acoustic": False},
    "conflicting_signals": {"genre": "metal", "mood": "sad", "energy": 0.95, "likes_acoustic": True},
    "diverse_hiphop_anxious": {"genre": "hip-hop", "mood": "anxious", "energy": 0.70, "likes_acoustic": False},
    "diverse_reggae_playful": {"genre": "reggae", "mood": "playful", "energy": 0.60, "likes_acoustic": False},
    "diverse_rnb_romantic": {"genre": "r&b", "mood": "romantic", "energy": 0.52, "likes_acoustic": False},
}


# Third-party libraries that log routine request/config details at INFO level.
# Our own "agent" logger already captures the information that matters (e.g. the
# full error message when a Gemini call fails), so this noise just gets in the way.
_NOISY_THIRD_PARTY_LOGGERS = ["google_genai", "google_genai.models", "httpx2", "httpcore2"]


def _configure_logging() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(LOGS_DIR, "agent.log")),
            logging.StreamHandler(sys.stdout),
        ],
    )
    for logger_name in _NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def print_recommendations(recommendations) -> None:
    for rank, (song, score, explanation) in enumerate(recommendations, start=1):
        print(f"\n{rank}. {song['title']} by {song['artist']}")
        print(f"   Score: {score:.2f}")
        print("   Reasons:")
        for reason in explanation.split("; "):
            print(f"     - {reason}")


def run_profile(name: str, user_prefs: dict, songs, k: int = 3) -> None:
    print(f"\n{'=' * 40}")
    print(f"Profile: {name} -> {user_prefs}")
    print("=" * 40)
    try:
        recommendations = recommend_songs(user_prefs, songs, k=k)
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        return
    print_recommendations(recommendations)


def _format_prefs(prefs: dict) -> str:
    genre = prefs.get("genre") or "unspecified"
    mood = prefs.get("mood") or "unspecified"
    energy = prefs.get("energy")
    energy_str = f"{energy:.2f}" if energy is not None else "unspecified"
    likes_acoustic = prefs.get("likes_acoustic")
    acoustic = "unspecified" if likes_acoustic is None else ("yes" if likes_acoustic else "no")
    return f"genre={genre} mood={mood} energy={energy_str} acoustic={acoustic}"


def print_trace(trace) -> None:
    print("\nAgent trace:")
    for step in trace:
        if step["step"] == "plan":
            print(f"  [plan]  {_format_prefs(step['prefs'])}")
            if step.get("note"):
                print(f"          note: {step['note']}")
        elif step["step"] == "act":
            print(f"  [act]   top score {step['top_score']:.2f}")
        elif step["step"] == "check":
            status = "ok" if step["good_enough"] else "weak"
            print(f"  [check] {status} - {step['reason']}")
        elif step["step"] == "retry":
            print(f"  [retry] {_format_prefs(step['prefs_used'])} -> top score {step['top_score']:.2f}")


def run_agentic_chat(songs) -> None:
    client = build_gemini_client()
    print("\nDescribe what you want to listen to (blank line to quit).")
    while True:
        try:
            user_text = input("\n> ").strip()
        except EOFError:
            break
        if not user_text:
            break

        print("  (thinking...)", flush=True)
        recommendations, trace = agentic_recommend(user_text, songs, k=3, client=client)

        print("-" * 40)
        print_trace(trace)
        print("\nRecommendations:")
        print_recommendations(recommendations)
        print("-" * 40)


def main() -> None:
    load_dotenv(ENV_PATH)
    _configure_logging()

    songs = load_songs(SONGS_CSV_PATH)

    if "--chat" in sys.argv:
        run_agentic_chat(songs)
        return

    for name, user_prefs in PROFILES.items():
        run_profile(name, user_prefs, songs)
    print()


if __name__ == "__main__":
    main()
