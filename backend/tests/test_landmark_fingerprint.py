from app.services.landmark_fingerprint import compare_landmark_fingerprints

def test_landmark_similarity_is_bounded():
    query={"hashes":[{"hash":"a"},{"hash":"b"},{"hash":"c"}]}
    assert compare_landmark_fingerprints(query,["a","b","x"]) == 2*2/6
    assert 0 <= compare_landmark_fingerprints(query,["z"]) <= 1

def test_empty_fingerprints_return_zero():
    assert compare_landmark_fingerprints({"hashes":[]},["a"]) == 0
