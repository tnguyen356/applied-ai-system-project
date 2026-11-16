# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agentic Workflow (SF8)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

Add an agentic workflow stretch feature to the recommender: a plan -> act -> check loop
that turns a free-text request (instead of a fixed profile dict) into recommendations,
using the existing `score_song`/`recommend_songs` logic as the deterministic "act" step,
and self-corrects (retries with a related genre/mood) when the first pass is a weak match.

**Prompts used:**

- "I want to expand on my music recommender, based on these requirements, what is one
  feature that will be suitable for my recommender and why?" (pasted the assignment's
  4-option feature list)
- "go more details into 'plan', explain the why and how in the decision"
- "what if the user wants something that isnt on the list?"
- "option 2 and then implement" (after discussing how to surface conflicting user signals)
- "with this new logic, what happened if user enters conflicting mood?"

**What did the agent generate or change?**

- `src/agent.py` (new) — `interpret_request` (plan step, Gemini-backed with a keyword
  fallback), `_validate_and_clean` (guardrail against hallucinated genres/moods and
  malformed fields), `evaluate_recommendations` (check step), `agentic_recommend`
  (the orchestration loop), `build_gemini_client`.
- `src/main.py` — added a `--chat` mode that runs the agentic loop interactively and
  prints the plan/act/check/retry trace; added logging setup.
- `tests/test_agent.py` (new) — 6 tests covering fallback parsing, validation, and the
  retry loop, all offline (no live API calls).
- `requirements.txt` — added `google-genai`, `python-dotenv`.
- `.env.example`, `.gitignore` — API key handling.
- `README.md` — setup/usage for the agentic mode.

**What did you verify or fix manually?**

Ran the test suite and the `--chat` CLI by hand against the conflicting-mood case I'd
asked about ("something happy but also kind of melancholic, chill pop"). Caught a real
bug this way: the first version of the keyword fallback picked a mood using the
catalog's alphabetical order, but the explanation it printed claimed the pick "appeared
first in your text" — that was false for that input (the picked mood actually appeared
last). Fixed `_keyword_fallback_parse` to sort matches by their real position in the
text (`sorted(..., key=text.index)`) so the note the user sees is actually true, then
re-ran the CLI to confirm the explanation matched the input. Also confirmed the dual
import style (`from recommender import ...` vs `from src.recommender import ...`) was
needed because `main.py` runs as a script while `tests/` imports the package - the first
test run failed with `ModuleNotFoundError` until I added the try/except import.

---

## Design Pattern (SF10)

> Document how AI helped you choose or implement a design pattern.

**Which design pattern did you use?**

<!-- e.g., Strategy, Factory, Observer, etc. -->

**How did AI help you brainstorm or implement it?**

<!-- Describe the conversation or suggestions that led to your decision -->

**How does the pattern appear in your final code?**

<!-- Point to the relevant class or method -->
