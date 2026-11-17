"""
Streamlit front end for the Music Recommender's agentic chat mode.

Pure UI layer: all interpretation and scoring logic lives in src/agent.py and
src/recommender.py. This file only renders agentic_recommend()'s output.
"""

import logging
import os
import sys

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from agent import agentic_recommend, build_gemini_client  # noqa: E402
from recommender import load_songs  # noqa: E402

SONGS_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "songs.csv")
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

# Same noisy loggers main.py silences, so the log file reads the same either way.
_NOISY_THIRD_PARTY_LOGGERS = ["google_genai", "google_genai.models", "httpx2", "httpcore2"]


@st.cache_resource(show_spinner=False)
def configure_logging() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(os.path.join(LOGS_DIR, "agent.log"), encoding="utf-8")],
    )
    for logger_name in _NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


@st.cache_resource(show_spinner="Loading catalog...")
def get_songs():
    load_dotenv(ENV_PATH)
    return load_songs(SONGS_CSV_PATH)


@st.cache_resource(show_spinner=False)
def get_client():
    return build_gemini_client()


def format_prefs(prefs: dict) -> str:
    mood = prefs.get("mood") or "unspecified"
    energy = prefs.get("energy")
    energy_str = f"{energy:.2f}" if energy is not None else "unspecified"
    tempo = prefs.get("tempo_bpm")
    tempo_str = f"{tempo:.0f} bpm" if tempo is not None else "unspecified"
    danceability = prefs.get("danceability")
    danceability_str = f"{danceability:.2f}" if danceability is not None else "unspecified"
    likes_acoustic = prefs.get("likes_acoustic")
    acoustic = "unspecified" if likes_acoustic is None else ("yes" if likes_acoustic else "no")
    return (
        f"mood=**{mood}**  · energy={energy_str}  · tempo={tempo_str}  · "
        f"danceability={danceability_str}  · acoustic={acoustic}"
    )


def render_trace(trace: list) -> None:
    with st.expander("Agent trace (plan → act → check → retry)"):
        for step in trace:
            if step["step"] == "plan":
                st.markdown(f"**Plan** — {format_prefs(step['prefs'])}")
                if step.get("note"):
                    st.caption(f"Note: {step['note']}")
            elif step["step"] == "act":
                st.markdown(f"**Act** — top score {step['top_score']:.2f}")
            elif step["step"] == "check":
                if step["good_enough"]:
                    st.success(step["reason"])
                else:
                    st.warning(step["reason"])
            elif step["step"] == "retry":
                st.info(
                    f"**Retry** — {format_prefs(step['prefs_used'])} "
                    f"→ top score {step['top_score']:.2f}"
                )


def render_recommendations(recommendations: list) -> None:
    if not recommendations:
        st.warning("No recommendations returned.")
        return
    for rank, (song, score, explanation) in enumerate(recommendations, start=1):
        with st.container(border=True):
            st.markdown(f"**{rank}. {song['title']}** — {song['artist']}")
            st.caption(f"Score: {score:.2f}")
            for reason in explanation.split("; "):
                st.markdown(f"- {reason}")


def main() -> None:
    st.set_page_config(page_title="Music Recommender")
    configure_logging()

    st.title("Music Recommender")
    st.caption("Describe what you want to hear in plain language; the agent interprets it, "
               "scores the catalog deterministically, and retries with a related mood if the first pass is weak.")

    songs = get_songs()
    client = get_client()

    with st.sidebar:
        st.metric("Catalog size", f"{len(songs):,} tracks")
        if client is not None:
            st.success("Gemini planner active")
        else:
            st.warning("No GEMINI_API_KEY set — using the keyword fallback parser")
        k = st.slider("Number of recommendations", min_value=1, max_value=10, value=3)
        known_moods = sorted({song["mood"] for song in songs})
        st.caption("Catalog moods: " + ", ".join(known_moods))

    if "history" not in st.session_state:
        st.session_state.history = []

    for turn in st.session_state.history:
        with st.chat_message(turn["role"]):
            if turn["role"] == "user":
                st.markdown(turn["content"])
            else:
                render_trace(turn["trace"])
                render_recommendations(turn["recommendations"])

    user_text = st.chat_input("Describe what you want to listen to...")
    if user_text:
        st.session_state.history.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                recommendations, trace = agentic_recommend(user_text, songs, k=k, client=client)
            render_trace(trace)
            render_recommendations(recommendations)
        st.session_state.history.append(
            {"role": "assistant", "trace": trace, "recommendations": recommendations}
        )


main()
