from app.services.collaborative import rank_collaborative
from app.services.recommendation import rank_recommendations, catalog_coverage
from tests.test_collaborative import tiny_model


def catalog():
    return [
        {"id":"new-a","title":"A","artist":"B-Ray","album":"Album","genres":[],"moods":[],"language":"other"},
        {"id":"new-b","title":"B","artist":"B-Ray & AMEE","album":"Single","genres":[],"moods":[],"language":"other"},
        {"id":"new-c","title":"C","artist":"B-Ray","album":"Album","genres":[],"moods":[],"language":"other"},
        {"id":"wrong","title":"Wrong","artist":"B-Ray","genres":["rock"],"moods":["happy"],"language":"en"},
    ]


def test_favorite_artist_is_not_assumed_to_have_been_heard():
    rows,method,_=rank_collaborative(catalog(),{"artists":["b-ray"]},[],tiny_model(),method="hybrid")
    assert rows and any(row["id"]=="new-a" for row in rows)
    assert method=="content_based"
    assert all("Người nghe" not in " ".join(row["reasons"]) for row in rows)


def test_collaboration_counts_as_artist_match_and_blocking_any_participant_works():
    rows=rank_recommendations(catalog(),{"artists":["bray"],"blocked_artists":["AMEE"]})
    assert all(row["id"]!="new-b" for row in rows)
    assert catalog_coverage([catalog()[1]],{"artists":["b ray"]})["missing_artists"]==[]


def test_known_conflicting_labels_remain_excluded_but_missing_labels_are_not_invented():
    rows,_,_=rank_collaborative(catalog(),{"artists":["B Ray"],"genres":["hip-hop"],"moods":["sad"],"languages":["vi"]},[],tiny_model(),method="hybrid")
    assert rows and all(row["id"]!="wrong" for row in rows)
    assert all(row["language"]=="other" and row["moods"]==[] for row in rows)
    assert all("Ngôn ngữ phù hợp" not in row["reasons"] for row in rows)


def test_newly_liked_song_gets_content_neighbors_without_fake_collaborative_counts():
    rows,method,_=rank_collaborative(catalog(),{},[{"track_id":"new-a","action":"like"}],tiny_model(),method="hybrid")
    assert method=="content_based"
    assert rows and rows[0]["id"]=="new-c"
    assert all(row["id"]!="new-a" for row in rows)


def test_negative_feedback_is_not_reintroduced_as_an_artist_seed():
    rows,_,_=rank_collaborative(catalog(),{"artists":["B-Ray"]},[{"track_id":"new-b","action":"dislike"}],tiny_model(),method="hybrid")
    assert all(row["id"]!="new-b" for row in rows)


def test_duplicate_catalog_entries_do_not_repeat_or_recommend_a_liked_song_again():
    entries=catalog()+[{**catalog()[0],"id":"another-source"}]
    rows,_,_=rank_collaborative(entries,{},[{"track_id":"new-a","action":"like"}],tiny_model(),method="hybrid")
    assert rows and all(row["title"]!="A" for row in rows)
    rows,_,_=rank_collaborative(entries,{"artists":["B-Ray"]},[{"track_id":"new-a","action":"dislike"}],tiny_model(),method="hybrid")
    assert all(row["title"]!="A" for row in rows)


def test_filtered_neighbors_do_not_hide_relevant_metadata_fallback():
    from tests.test_recommendation_integration import T1, T2, T3, example_catalog

    # There is a learned neighbour, but the chosen language excludes it.
    model = tiny_model()
    model["neighbors"][T1] = [[T2, 0.8]]
    rows, method, _ = rank_collaborative(example_catalog(), {"languages": ["vi"]},
                                         [{"track_id": T1, "action": "like"}], model)
    assert method == "metadata"
    assert [row["id"] for row in rows] == [T3]
