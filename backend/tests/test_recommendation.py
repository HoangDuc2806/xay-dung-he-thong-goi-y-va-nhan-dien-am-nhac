from app.services.recommendation import rank_recommendations
from app.routers.recommendations import Preferences
from app.services.recommendation import catalog_coverage

def test_preferences_normalize_and_deduplicate():
    assert Preferences(genres=["Pop", "pop", " "]).genres == ["pop"]

def test_rank_catalog_prefers_matching_genre_and_mood():
    rows=[
        {"id":"1","title":"A","genres":["pop"],"moods":["chill"],"language":"vi"},
        {"id":"2","title":"B","genres":["rock"],"moods":["party"],"language":"en"},
    ]
    ranked=rank_recommendations(rows,{"genres":["pop"],"moods":["chill"],"languages":["vi"]})
    assert ranked[0]["id"] == "1"
    assert ranked[0]["score"] == 1.0
    assert "fingerprint_hashes" not in ranked[0]

def test_empty_preferences_do_not_fake_personalization():
    result=rank_recommendations([{"id":"1","title":"A","genres":["pop"]}],{})
    assert result[0]["score"] == 0


def test_missing_favorite_artist_does_not_return_zero_score_personalization():
    rows=[{"id":"1","title":"Song","artist":"Queen","genres":["rock"],"moods":["energetic"],"language":"en"}]
    assert rank_recommendations(rows,{"artists":["bray"],"discovery_level":100}) == []
    coverage=catalog_coverage(rows,{"artists":["bray"]})
    assert coverage["catalog_size"] == 1
    assert coverage["missing_artists"] == ["bray"]
    assert coverage["available_languages"] == ["en"]


def test_artist_matching_ignores_punctuation_and_spacing_but_not_substrings():
    rows=[{"id":"1","title":"Song","artist":"B-Ray"},
          {"id":"2","title":"Another","artist":"Brayden"}]
    result=rank_recommendations(rows,{"artists":["bray"]})
    assert [row["id"] for row in result] == ["1"]
    assert catalog_coverage(rows,{"artists":["B Ray"]})["missing_artists"] == []


def test_blocked_artist_uses_the_same_name_normalization():
    rows=[{"id":"1","title":"Song","artist":"B-Ray"}]
    assert rank_recommendations(rows,{"blocked_artists":["bray"]}) == []


def test_diversity_changes_artist_limit_without_inventing_relevance():
    rows=[{"id":str(i),"title":str(i),"artist":"Queen","genres":["rock"]} for i in range(4)]
    assert len(rank_recommendations(rows,{"genres":["rock"],"discovery_level":0})) == 3
    assert len(rank_recommendations(rows,{"genres":["rock"],"discovery_level":100})) == 1
    assert rank_recommendations(rows,{"genres":["jazz"],"discovery_level":100}) == []
    assert len(rank_recommendations(rows,{},diversify=False)) == 4


def test_positive_feedback_keeps_a_reason_and_negative_feedback_excludes_tracks():
    rows=[{"id":"1","title":"One","artist":"A","genres":["rock"]},
          {"id":"2","title":"Two","artist":"B","genres":["rock"]},
          {"id":"3","title":"Three","artist":"C","genres":["jazz"]}]
    result=rank_recommendations(rows,{},[{"track_id":"1","action":"like"},{"track_id":"2","action":"skip"}])
    assert [row["id"] for row in result] == ["1"]
    assert result[0]["feedback_action"] == "like"
    assert result[0]["score"] > 0
    assert "Tương đồng" in result[0]["reasons"][0]


def test_language_and_mood_choices_are_respected_even_with_positive_feedback():
    rows=[{"id":"1","title":"Vietnamese sad","artist":"A","language":"vi","moods":["sad"],"genres":["pop"]},
          {"id":"2","title":"English sad","artist":"B","language":"en","moods":["sad"],"genres":["pop"]},
          {"id":"3","title":"Vietnamese happy","artist":"C","language":"vi","moods":["happy"],"genres":["pop"]}]
    result=rank_recommendations(rows,{"languages":["vi"],"moods":["sad"]},[{"track_id":"2","action":"like"}])
    assert [row["id"] for row in result] == ["1"]
