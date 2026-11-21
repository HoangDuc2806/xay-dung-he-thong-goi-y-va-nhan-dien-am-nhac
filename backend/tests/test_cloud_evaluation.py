from tools.evaluate_cloud_recognition import classify, summarize


def test_metadata_agreement_requires_title_and_artist():
    assert classify([], "Song", "Artist") == "not_found"
    assert classify([{"title":"SONG!", "artists":["Artist"]}], "Song", "Artist") == "metadata_match"
    assert classify([{"title":"Song", "artists":["Other performer"]}], "Song", "Artist") == "needs_review"
    assert classify([{"title":"Song (Live)", "artists":["Artist"]}], "Song", "Artist") == "needs_review"


def test_api_errors_and_interrupted_requests_are_not_recognition_misses():
    result = summarize([{"status":"metadata_match", "elapsed_ms":10},
                        {"status":"not_found", "elapsed_ms":20},
                        {"status":"needs_review", "elapsed_ms":30},
                        {"status":"error", "elapsed_ms":100}, {"status":"started"}])
    assert result["attempted"] == 5 and result["completed"] == 3
    assert result["metadata_match_percent_completed"] == 33.33
    assert result["errors"] == 1 and result["interrupted"] == 1
    assert result["not_found"] == 1 and result["latency_p50_ms"] == 20
    assert summarize([])["metadata_match_percent_completed"] is None
