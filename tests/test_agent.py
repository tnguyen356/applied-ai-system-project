from src.agent import (
    MIN_ACCEPTABLE_SCORE,
    _keyword_fallback_parse,
    _validate_and_clean,
    agentic_recommend,
    evaluate_recommendations,
)

SONGS = [
    {
        "id": 1,
        "title": "Sunny Pop Anthem",
        "artist": "Test Artist",
        "genre": "pop",
        "mood": "happy",
        "energy": 0.8,
        "tempo_bpm": 120,
        "valence": 0.9,
        "danceability": 0.8,
        "acousticness": 0.1,
    },
    {
        "id": 2,
        "title": "Rainy Day Blues",
        "artist": "Test Artist",
        "genre": "blues",
        "mood": "melancholic",
        "energy": 0.3,
        "tempo_bpm": 70,
        "valence": 0.3,
        "danceability": 0.4,
        "acousticness": 0.8,
    },
]

KNOWN_GENRES = ["blues", "pop"]
KNOWN_MOODS = ["happy", "melancholic"]


def test_keyword_fallback_picks_mood_by_order_of_appearance_not_catalog_order():
    # "melancholic" appears before "happy" in the text, even though "happy"
    # sorts first alphabetically in KNOWN_MOODS - the fallback must honor text order.
    parsed = _keyword_fallback_parse(
        "feeling melancholic today but also kind of happy, give me some pop",
        KNOWN_GENRES,
        KNOWN_MOODS,
    )
    assert parsed["mood"] == "melancholic"
    assert "melancholic" in parsed["note"]
    assert "happy" in parsed["note"]


def test_keyword_fallback_no_note_when_moods_dont_conflict():
    parsed = _keyword_fallback_parse("upbeat happy pop please", KNOWN_GENRES, KNOWN_MOODS)
    assert parsed["mood"] == "happy"
    assert parsed["note"] is None


def test_validate_and_clean_drops_hallucinated_genre():
    cleaned = _validate_and_clean(
        {
            "genre": "k-pop",  # not in catalog
            "mood": "happy",
            "energy": 0.5,
            "likes_acoustic": False,
            "fallback_genres": ["pop", "country"],  # country isn't real either
            "fallback_moods": [],
            "note": None,
        },
        KNOWN_GENRES,
        KNOWN_MOODS,
    )
    assert cleaned["genre"] is None
    assert cleaned["fallback_genres"] == ["pop"]


def test_validate_and_clean_clamps_out_of_range_energy():
    cleaned = _validate_and_clean(
        {"genre": "pop", "mood": "happy", "energy": 5.0, "likes_acoustic": "yes"},
        KNOWN_GENRES,
        KNOWN_MOODS,
    )
    assert cleaned["energy"] == 1.0
    assert cleaned["likes_acoustic"] is True


def test_evaluate_recommendations_flags_weak_top_score():
    weak = [({"title": "x"}, MIN_ACCEPTABLE_SCORE - 0.5, "reasons")]
    strong = [({"title": "y"}, MIN_ACCEPTABLE_SCORE + 0.5, "reasons")]

    assert evaluate_recommendations(weak)["good_enough"] is False
    assert evaluate_recommendations(strong)["good_enough"] is True
    assert evaluate_recommendations([])["good_enough"] is False


def test_agentic_recommend_retries_when_first_pass_is_weak():
    # No client passed -> uses the deterministic keyword fallback (reproducible, no network).
    recommendations, trace = agentic_recommend(
        "something melancholic and bluesy", SONGS, k=1, client=None
    )

    steps = [t["step"] for t in trace]
    assert "plan" in steps and "act" in steps and "check" in steps

    top_song, top_score, _ = recommendations[0]
    assert top_song["genre"] == "blues"
    assert top_score >= MIN_ACCEPTABLE_SCORE
