"""TF-IDF/cosine over independent metadata, not Spotify/audio features."""
from collections import Counter, defaultdict
import math
import unicodedata
import numpy as np
from functools import lru_cache
from app.services.recommendation import artist_keys


def content_tokens(item: dict) -> set[str]:
    def key(value):
        return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())
    artist, album = key(item.get("artist") or ""), key(item.get("album") or "")
    tokens = {"artist:" + name for name in artist_keys(item.get("artist") or "")}
    if album:
        tokens.add("album:" + artist + ":" + album)
    for field in ("genres", "moods", "tags"):
        tokens.update(field + ":" + key(value) for value in item.get(field) or [] if key(value))
    language = item.get("language")
    if language and language not in ("other", "und"):
        tokens.add("language:" + key(language))
    return tokens


def fit_content(items: list[dict], neighbors=50) -> dict:
    """Binary term frequency, smoothed IDF, L2 norm, top cosine neighbours."""
    ordered = sorted(items, key=lambda item: str(item["id"]))
    documents = [content_tokens(item) for item in ordered]
    frequency = Counter(token for document in documents for token in document)
    vocabulary = {token: index for index, token in enumerate(sorted(frequency))}
    matrix = np.zeros((len(items), len(vocabulary)), dtype=np.float32)
    for row, document in enumerate(documents):
        for token in document:
            matrix[row, vocabulary[token]] = math.log((1 + len(items)) / (1 + frequency[token])) + 1
    matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
    graph = {}
    # Bound similarity memory to a batch instead of allocating N x N for large vocabularies.
    for begin in range(0, len(items), 128):
        similarities = matrix[begin:begin+128] @ matrix.T
        for offset, scores in enumerate(similarities):
            row = begin + offset
            scores[row] = 0
            order = np.argsort(-scores, kind="stable")[:neighbors]
            graph[str(ordered[row]["id"])] = [[str(ordered[index]["id"]), round(float(scores[index]), 6)]
                                             for index in order if scores[index] > 0]
    return graph


def catalog_content_graph(items: list[dict]):
    """Cache only public metadata, not personal preferences; include untrained/new tracks."""
    signature=tuple(sorted((str(row["id"]),str(row.get("artist") or ""),str(row.get("album") or ""),
                            str(row.get("language") or "other"),tuple(sorted(row.get("genres") or [])),
                            tuple(sorted(row.get("moods") or [])),tuple(sorted(row.get("tags") or []))) for row in items))
    return _catalog_graph(signature)


@lru_cache(maxsize=1)
def _catalog_graph(signature):
    documents = {
        key: content_tokens({"artist": artist, "album": album, "language": language,
                             "genres": genres, "moods": moods, "tags": tags})
        for key, artist, album, language, genres, moods, tags in signature
    }
    return ContentIndex(documents)


class ContentIndex:
    """Sparse TF-IDF index exposing neighbours only for requested seed tracks."""

    def __init__(self, documents):
        frequency = Counter(token for tokens in documents.values() for token in tokens)
        idf = {token: math.log((1 + len(documents)) / (1 + count)) + 1
               for token, count in frequency.items()}
        self.vectors = {}
        self.postings = defaultdict(list)
        for key, tokens in documents.items():
            norm = math.sqrt(sum(idf[token] ** 2 for token in sorted(tokens)))
            weights = {token: idf[token] / norm for token in sorted(tokens)}
            self.vectors[key] = weights
            for token, weight in weights.items():
                self.postings[token].append((key, weight))
        self._neighbors = lru_cache(maxsize=2048)(self._score_neighbors)

    def __iter__(self):
        return iter(self.vectors)

    def __contains__(self, key):
        return key in self.vectors

    def get(self, key, default=()):
        return self._neighbors(key) if key in self else default

    def _score_neighbors(self, key):
        scores = Counter()
        for token, weight in self.vectors[key].items():
            for candidate, other_weight in self.postings[token]:
                if candidate != key:
                    scores[candidate] += weight * other_weight
        return tuple(sorted(((candidate, round(score, 6)) for candidate, score in scores.items()),
                            key=lambda row: (-row[1], row[0]))[:50])
