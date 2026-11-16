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

KNOWN_MOODS = ["happy", "melancholic"]


def test_keyword_fallback_picks_mood_by_order_of_appearance_not_catalog_order():
    # "melancholic" appears before "happy" in the text, even though "happy"
    # sorts first alphabetically in KNOWN_MOODS - the fallback must honor text order.
    parsed = _keyword_fallback_parse(
        "feeling melancholic today but also kind of happy and upbeat",
        KNOWN_MOODS,
    )
    assert parsed["mood"] == "melancholic"
    assert "melancholic" in parsed["note"]
    assert "happy" in parsed["note"]


def test_keyword_fallback_no_note_when_moods_dont_conflict():
    parsed = _keyword_fallback_parse("upbeat happy please", KNOWN_MOODS)
    assert parsed["mood"] == "happy"
    assert parsed["note"] is None


def test_keyword_fallback_infers_tempo_and_danceability_from_text():
    parsed = _keyword_fallback_parse("something slow and mellow", KNOWN_MOODS)
    assert parsed["tempo_bpm"] == 70.0
    assert parsed["danceability"] == 0.3

    parsed_unspecified = _keyword_fallback_parse("happy music please", KNOWN_MOODS)
    assert parsed_unspecified["tempo_bpm"] is None
    assert parsed_unspecified["danceability"] is None


def test_keyword_fallback_maps_common_synonym_to_catalog_mood():
    # "chill" isn't itself one of the catalog's mood labels, but it should still
    # resolve to the closest real one (not fall through to None).
    parsed = _keyword_fallback_parse("something chill please", KNOWN_MOODS + ["dreamy"])
    assert parsed["mood"] == "dreamy"


def test_keyword_fallback_no_fallback_moods_when_mood_unresolved():
    # With no mood word or synonym match, there's no sensible "related mood" to
    # retry with - fallback_moods must stay empty rather than picking an arbitrary one.
    parsed = _keyword_fallback_parse("some music please", KNOWN_MOODS)
    assert parsed["mood"] is None
    assert parsed["fallback_moods"] == []


def test_validate_and_clean_drops_hallucinated_mood():
    cleaned = _validate_and_clean(
        {
            "mood": "furious",  # not in catalog
            "energy": 0.5,
            "likes_acoustic": False,
            "fallback_moods": ["happy", "angsty"],  # "angsty" isn't real either
            "note": None,
        },
        KNOWN_MOODS,
    )
    assert cleaned["mood"] is None
    assert cleaned["fallback_moods"] == ["happy"]


def test_validate_and_clean_clamps_tempo_and_drops_invalid_danceability():
    cleaned = _validate_and_clean(
        {
            "mood": "happy",
            "energy": 0.5,
            "tempo_bpm": 500,  # above range, should clamp to the max
            "danceability": "not-a-number",  # invalid, should become None
            "likes_acoustic": False,
            "fallback_moods": [],
            "note": None,
        },
        KNOWN_MOODS,
    )
    assert cleaned["tempo_bpm"] == 220.0
    assert cleaned["danceability"] is None


def test_validate_and_clean_clamps_out_of_range_energy():
    cleaned = _validate_and_clean(
        {"mood": "happy", "energy": 5.0, "likes_acoustic": "yes"},
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
        "something melancholic and slow", SONGS, k=1, client=None
    )

    steps = [t["step"] for t in trace]
    assert "plan" in steps and "act" in steps and "check" in steps

    top_song, top_score, _ = recommendations[0]
    assert top_song["genre"] == "blues"
    assert top_score >= MIN_ACCEPTABLE_SCORE
