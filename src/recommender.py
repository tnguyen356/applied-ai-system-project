import csv
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool

class Recommender:
    """
    OOP implementation of the recommendation logic.
    Required by tests/test_recommender.py
    """
    def __init__(self, songs: List[Song]):
        self.songs = songs

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        # TODO: Implement recommendation logic
        return self.songs[:k]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        # TODO: Implement explanation logic
        return "Explanation placeholder"

# The Spotify tracks dataset (data/songs.csv) has no mood label, so one is derived
# from valence/energy. Tiers are deliberately coarse (3x3) and the labels are drawn
# from agent.py's MOOD_ENERGY_DEFAULTS so the agent's mood vocabulary stays meaningful.
MOOD_BY_QUADRANT = {
    ("high", "high"): "euphoric",
    ("high", "mid"): "triumphant",
    ("high", "low"): "anxious",
    ("mid", "high"): "happy",
    ("mid", "mid"): "focused",
    ("mid", "low"): "moody",
    ("low", "high"): "romantic",
    ("low", "mid"): "dreamy",
    ("low", "low"): "melancholic",
}


def _tier(value: float, low_max: float, mid_max: float) -> str:
    if value < low_max:
        return "low"
    if value < mid_max:
        return "mid"
    return "high"


def _infer_mood(valence: float, energy: float) -> str:
    energy_tier = _tier(energy, 0.4, 0.7)
    valence_tier = _tier(valence, 0.4, 0.6)
    return MOOD_BY_QUADRANT[(energy_tier, valence_tier)]


def load_songs(csv_path: str) -> List[Dict]:
    """Reads the Spotify tracks dataset CSV into a list of dicts using this
    project's field names (title/artist/genre/mood/tempo_bpm/...), deriving
    mood from valence/energy since the raw data has no mood column."""
    songs = []
    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for index, row in enumerate(reader):
            energy = float(row["energy"])
            valence = float(row["valence"])
            songs.append({
                "id": index,
                "title": row["track_name"],
                "artist": row["artists"],
                "genre": row["track_genre"],
                "mood": _infer_mood(valence, energy),
                "energy": energy,
                "tempo_bpm": float(row["tempo"]),
                "valence": valence,
                "danceability": float(row["danceability"]),
                "acousticness": float(row["acousticness"]),
                "spotify_url": f"https://open.spotify.com/track/{row['track_id']}",
            })
    return songs

MOOD_WEIGHT = 2.0
ENERGY_WEIGHT = 1.0
TEMPO_WEIGHT = 1.0
DANCEABILITY_WEIGHT = 1.0
ACOUSTIC_WEIGHT = 0.5

# Used to turn a tempo difference in BPM into a 0-1 closeness score - two tracks
# this far apart in tempo (or more) are treated as having nothing in common tempo-wise.
TEMPO_RANGE_BPM = 200.0

def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """Scores a song against user preferences and returns the score with matching reasons.

    There's no reliable genre label to match on (the catalog's genres are mostly
    one-offs), so instead of an exact-match genre term, this scores closeness on
    tempo and danceability - audio features that stand in for "sounds similar"."""
    score = 0.0
    reasons = []

    if user_prefs.get("mood") == song.get("mood"):
        score += MOOD_WEIGHT
        reasons.append(f"Matches your favorite mood ({song.get('mood')})")

    target_energy = user_prefs.get("energy")
    if target_energy is not None:
        energy_closeness = 1 - abs(song.get("energy", 0.0) - target_energy)
        score += energy_closeness * ENERGY_WEIGHT
        if energy_closeness >= 0.8:
            reasons.append("Energy level is close to what you're looking for")

    target_tempo = user_prefs.get("tempo_bpm")
    if target_tempo is not None:
        tempo_closeness = 1 - min(1.0, abs(song.get("tempo_bpm", 0.0) - target_tempo) / TEMPO_RANGE_BPM)
        score += tempo_closeness * TEMPO_WEIGHT
        if tempo_closeness >= 0.8:
            reasons.append("Tempo is close to what you're looking for")

    target_danceability = user_prefs.get("danceability")
    if target_danceability is not None:
        danceability_closeness = 1 - abs(song.get("danceability", 0.0) - target_danceability)
        score += danceability_closeness * DANCEABILITY_WEIGHT
        if danceability_closeness >= 0.8:
            reasons.append("Danceability is close to what you're looking for")

    likes_acoustic = user_prefs.get("likes_acoustic", False)
    acousticness = song.get("acousticness", 0.0)
    if likes_acoustic is None:
        pass  # no stated preference - don't reward either way
    elif likes_acoustic and acousticness >= 0.5:
        score += ACOUSTIC_WEIGHT
        reasons.append("Has an acoustic sound you tend to enjoy")
    elif not likes_acoustic and acousticness < 0.5:
        score += ACOUSTIC_WEIGHT
        reasons.append("Has a produced, non-acoustic sound matching your taste")

    return score, reasons

def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> List[Tuple[Dict, float, str]]:
    """Scores every song against user preferences and returns the top k, highest score first."""
    scored = [(song, *score_song(user_prefs, song)) for song in songs]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [
        (song, score, "; ".join(reasons) if reasons else "No strong matches found")
        for song, score, reasons in scored[:k]
    ]
