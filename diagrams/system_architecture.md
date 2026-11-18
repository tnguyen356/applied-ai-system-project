# System Architecture

Data flows left-to-right/top-to-bottom through four stages: a data layer that builds the
song catalog, an **input** (free text from the terminal or the Streamlit UI, or a fixed
profile), the **agent**'s plan → act → check loop, and an **output** of ranked, deduped,
explained recommendations with Spotify links. The green nodes at the bottom are where
humans or automated tests check the AI's output — offline unit tests validate the agent's
logic before it ships, manual exploratory testing against real language caught bugs the
tests missed, and every recommendation ships with a human-readable trace and reasons
instead of a bare score.

Mermaid source for this diagram also lives standalone at
[`system_architecture.mmd`](system_architecture.mmd).

```mermaid
flowchart TD
    subgraph DATA["Data Layer"]
        CSV[("data/songs.csv<br/>~114k Spotify tracks")]
        LOAD["load_songs()<br/>recommender.py<br/>maps columns, derives mood<br/>from a valence/energy quadrant,<br/>builds a spotify_url per track"]
        CATALOG[("Song catalog (in memory)<br/>title, artist, genre, mood,<br/>energy, tempo, danceability,<br/>valence, acousticness, spotify_url")]
        CSV --> LOAD --> CATALOG
    end

    subgraph INPUT["Input"]
        CLICHAT["Free-text request (terminal)<br/>e.g. 'something chill'<br/>main.py --chat"]
        WEBCHAT["Free-text request (browser)<br/>e.g. 'i want sleep music'<br/>app.py - Streamlit chat UI"]
        PROFILE["Fixed preference profile<br/>(PROFILES dict in main.py)"]
    end

    subgraph AGENT["Agent: plan -> act -> check  (agent.py)"]
        PLAN["PLAN: interpret_request()<br/>Gemini LLM, or a deterministic<br/>keyword-fallback parser if no<br/>API key / the call fails"]
        ACT["ACT: score_song / recommend_songs<br/>recommender.py<br/>weighted closeness scoring,<br/>deduped by spotify_url/id so the<br/>same track can't fill 2 top-k slots"]
        CHECK{"CHECK: evaluate_recommendations()<br/>top score >= 3.0 threshold?"}
        RETRY["RETRY (once)<br/>swap in the next fallback mood"]
        PLAN --> ACT --> CHECK
        CHECK -->|"no, weak match"| RETRY
        RETRY --> ACT
    end

    OUTPUT["Output<br/>Top-k ranked, deduped songs +<br/>plain-language match reasons +<br/>Spotify links + plan/act/check/retry trace"]

    subgraph HUMAN["Human & automated checks on AI output"]
        TESTS["pytest: test_agent.py + test_recommender.py<br/>12 offline tests validate the parser,<br/>mood inference, retry, and dedup logic<br/>BEFORE the agent is trusted"]
        MANUAL["Manual exploratory testing<br/>(real language via --chat / app.py)<br/>caught bugs unit tests missed: 'chill'<br/>and 'sleep music' resolving to no mood,<br/>a misconfigured Gemini model, and the<br/>same track filling 2 slots in one result"]
        REVIEW["Human reads the printed<br/>plan/act/check/retry trace and the<br/>per-song reasons before trusting a result<br/>(explainability, not a black box)"]
        LOG[("logs/agent.log<br/>audit trail of every<br/>plan/act/check/retry decision")]
    end

    CLICHAT --> PLAN
    WEBCHAT --> PLAN
    PROFILE --> ACT
    CATALOG --> ACT
    CATALOG --> PLAN
    CHECK -->|"yes, good enough"| OUTPUT
    OUTPUT --> REVIEW
    OUTPUT --> LOG
    TESTS -.->|"validates agent.py/recommender.py<br/>logic before it ships"| AGENT
    MANUAL -.->|"exercises the real<br/>end-to-end pipeline"| AGENT

    style TESTS fill:#2e7d32,color:#ffffff
    style MANUAL fill:#2e7d32,color:#ffffff
    style REVIEW fill:#2e7d32,color:#ffffff
    style LOG fill:#2e7d32,color:#ffffff
```
