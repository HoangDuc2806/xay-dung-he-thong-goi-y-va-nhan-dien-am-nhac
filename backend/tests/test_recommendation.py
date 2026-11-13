from app.services.recommendation import normalize_values, rank_catalog, ALLOWED_GENRES

def test_normalize_values_filters_and_deduplicates():
    assert normalize_values(["Pop", "pop", "not-a-genre"], ALLOWED_GENRES) == ["pop"]

def test_rank_catalog_prefers_matching_genre_and_mood():
    rows=[
        {"id":"1","title":"A","genres":["pop"],"moods":["chill"],"language":"vi"},
        {"id":"2","title":"B","genres":["rock"],"moods":["party"],"language":"en"},
    ]
    ranked=rank_catalog(rows,{"genres":["pop"],"moods":["chill"],"languages":["vi"]})
    assert ranked[0]["id"] == "1"
    assert ranked[0]["match_score"] == 1.0
    assert "fingerprint_hashes" not in ranked[0]

def test_empty_preferences_do_not_fake_personalization():
    result=rank_catalog([{"id":"1","title":"A","genres":["pop"]}],{})
    assert result[0]["match_score"] == 0
