"""Train and evaluate item-KNN from an official ListenBrainz JSON-lines dump.

Run from backend: python -m tools.train_recommender --help
Raw records stay local/ignored. The serving artifact contains no user IDs.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import tarfile
import numpy as np

from app.services.collaborative import listen_metadata, model_scores
from app.services.content_recommendation import fit_content


def read_dump(path):
    import zstandard
    with Path(path).open("rb") as source, zstandard.ZstdDecompressor().stream_reader(source) as stream:
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            for member in archive:
                if member.isfile() and member.name.endswith(".listens"):
                    with archive.extractfile(member) as file:
                        for line in file:
                            yield json.loads(line)


def listen_timestamp(listen):
    # API and official dump have different field names.
    return int(listen.get("listened_at") or listen.get("timestamp") or 0)


def fit(events: list[tuple[str, str, int]], *, neighbors=50, shrinkage=10.0, user_balance=0.0) -> dict:
    users = sorted({user for user, _, _ in events})
    items = sorted({item for _, item, _ in events})
    user_index, item_index = {v: i for i, v in enumerate(users)}, {v: i for i, v in enumerate(items)}
    matrix = np.zeros((len(users), len(items)), dtype=np.float32)
    for user, item, _ in events:
        matrix[user_index[user], item_index[item]] += 1
    binary = (matrix > 0).astype(np.float32)
    popularity = binary.sum(axis=0)
    np.log1p(matrix, out=matrix)
    if user_balance:
        matrix *= (1 + binary.sum(axis=1, keepdims=True)) ** -user_balance
    norm = np.linalg.norm(matrix, axis=0)
    matrix /= np.maximum(norm, 1e-12)
    similarity = matrix.T @ matrix
    support = binary.T @ binary
    # Shrink unreliable co-occurrences. No self-neighbours or single-user edges.
    similarity *= support / (support + shrinkage)
    similarity[support < 2] = 0
    np.fill_diagonal(similarity, 0)
    graph = {}
    for i, key in enumerate(items):
        indices = np.argsort(-similarity[i], kind="stable")[:neighbors]
        graph[key] = [[items[j], round(float(similarity[i, j]), 6)] for j in indices if similarity[i, j] > 0]
    return {"neighbors": graph, "popularity": {key: int(popularity[i]) for i, key in enumerate(items)}}


def temporal_split(events, fraction=0.8):
    cutoff = sorted(timestamp for _, _, timestamp in events)[min(len(events)-1, int(len(events)*fraction))]
    return [row for row in events if row[2] < cutoff], [row for row in events if row[2] >= cutoff], cutoff


def evaluate(model, train, test, k=10, *, methods=None, normalize_candidates=False,
             seed_catalog=None, added_items=frozenset()):
    profiles = defaultdict(Counter)
    for user, item, _ in train:
        profiles[user][item] += 1
    targets = defaultdict(set)
    all_targets = set()
    for user, item, _ in test:
        if user in profiles and item not in profiles[user]:
            targets[user].add(item)
            all_targets.add(item)
    def metrics(method):
        total = Counter()
        recommended = set()
        for user, relevant in targets.items():
            weights = {key: math.log1p(n) for key, n in profiles[user].items()
                       if seed_catalog is None or key in seed_catalog}
            candidates = model["neighbors"].keys() - profiles[user].keys() if normalize_candidates and method == "hybrid" else None
            scores = model_scores(model, weights, method, candidates=candidates) if method != "popularity" else model["popularity"]
            ranked = sorted((key for key in scores if key not in profiles[user]), key=lambda key: (-scores[key], key))[:k]
            hits = sum(key in relevant for key in ranked)
            dcg = sum(1 / math.log2(i+2) for i, key in enumerate(ranked) if key in relevant)
            ideal = sum(1 / math.log2(i+2) for i in range(min(k, len(relevant))))
            total["precision"] += hits/k
            total["recall"] += hits/len(relevant)
            total["ndcg"] += dcg/ideal
            total["hit_rate"] += bool(hits)
            if added_items:
                total["metadata_only_in_top10"] += sum(key in added_items for key in ranked)
            recommended.update(ranked)
        result = {**{name+f"@{k}": round(total[name]/max(1, len(targets)), 6) for name in ("precision", "recall", "ndcg", "hit_rate")},
                  "catalog_coverage": round(len(recommended)/max(1, len(model["neighbors"])), 6)}
        if added_items:
            result["mean_metadata_only_in_top10"] = round(total["metadata_only_in_top10"]/max(1, len(targets)), 6)
        return result
    if methods is None:
        methods = ("item_knn", "popularity", "content_based", "hybrid") if "content_neighbors" in model else ("item_knn", "popularity")
    return {"test_users": len(targets), "test_unseen_items": len(all_targets),
            "train_vocabulary_target_coverage": round(len(all_targets & model["neighbors"].keys())/max(1, len(all_targets)), 6),
            **{("popularity_baseline" if method == "popularity" else method): metrics(method) for method in methods}}


def tune_hybrid(train, metadata):
    tuning_train, validation, cutoff = temporal_split(train, fraction=0.85)
    vocabulary = {key for _, key, _ in tuning_train}
    content = fit_content([metadata[key] for key in vocabulary])
    trials = []
    # Include both a conservative baseline and settings that spread evidence
    # across more neighbours and reduce unusually active users' influence.
    for neighbors, shrinkage, user_balance in ((50, 10, 0), (100, 10, 0), (100, 5, .25), (150, 5, .25), (100, 20, .25)):
        config = dict(neighbors=neighbors, shrinkage=shrinkage, user_balance=user_balance)
        model = {**fit(tuning_train, **config), "content_neighbors": content}
        for weight in (.5, .7, .85, .95):
            model["hybrid_cf_weight"] = weight
            measured = evaluate(model, tuning_train, validation, methods=("hybrid",), normalize_candidates=True)
            trials.append({"fit": config, "hybrid_cf_weight": weight, **measured["hybrid"]})
    best = max(trials, key=lambda trial: (trial["ndcg@10"], trial["recall@10"]))
    return {"cutoff_utc": datetime.fromtimestamp(cutoff, timezone.utc).isoformat(),
            "selection_metric": "ndcg@10, then recall@10", "selected": best, "trials": trials}


def evaluate_catalog_expansion(train, test, metadata, selection):
    """Isolate metadata-only candidate coverage on the same chronological split."""
    keys = {key for _, key, _ in train}
    withheld = {key for key in keys if hashlib.sha256(key.encode()).digest()[0] < 51}
    initial = keys - withheld
    graph = fit([row for row in train if row[1] in initial], **selection["fit"])
    baseline = {**graph, "hybrid_cf_weight": selection["hybrid_cf_weight"],
                "content_neighbors": fit_content([metadata[key] for key in initial])}
    expanded = {**baseline, "neighbors": {**graph["neighbors"], **dict.fromkeys(withheld, ())},
                "content_neighbors": fit_content([metadata[key] for key in keys])}
    options = {"methods": ("hybrid",), "normalize_candidates": True, "seed_catalog": initial, "added_items": withheld}
    return {"protocol": "Hash-holdout of about 20% of training track IDs; same historical profiles, seen-item exclusions and test targets in both runs",
            "initial_catalog": len(initial), "metadata_only_catalog": len(withheld),
            "limitation": "All withheld items are made available from verified input metadata; live lookup coverage and latency are not simulated",
            "baseline": evaluate(baseline, train, test, **options),
            "with_metadata": evaluate(expanded, train, test, **options)}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("dump", type=Path)
    cli.add_argument("--source-url", required=True)
    cli.add_argument("--since", default="2026-10-13", help="Earliest listened-at date, UTC")
    cli.add_argument("--max-items", type=int, default=2000)
    cli.add_argument("--max-users", type=int, default=5000)
    cli.add_argument("--min-items-per-user", type=int, default=5)
    cli.add_argument("--output", type=Path, default=Path("artifacts/recommender.json"))
    cli.add_argument("--evaluate-catalog-expansion", action="store_true", help="Measure a metadata-only candidate holdout on the same test split")
    args = cli.parse_args()
    if not args.source_url.startswith("https://data.metabrainz.org/"):
        cli.error("Use an official MetaBrainz dump URL; this pipeline is not for Spotify data.")
    if not 10 <= args.max_items <= 5000 or not 10 <= args.max_users <= 10000:
        cli.error("max-items must be 10..5000 and max-users 10..10000")
    since = int(datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc).timestamp())
    events, metadata, metadata_time, raw = [], {}, {}, 0
    for listen in read_dump(args.dump):
        raw += 1
        # API uses listened_at; the official PostgreSQL listen dump uses timestamp.
        timestamp = listen_timestamp(listen)
        if timestamp < since:
            continue
        item = listen_metadata(listen)
        user = listen.get("user_id") or listen.get("user_name")
        if not item or user is None:
            continue
        # Never retain public usernames in artifacts or logs.
        user = hashlib.sha256(str(user).encode()).hexdigest()[:24]
        # Keep earliest metadata for train-only content features, not a future album label.
        if timestamp < metadata_time.get(item["id"], float("inf")):
            metadata[item["id"]] = item
            metadata_time[item["id"]] = timestamp
        events.append((user, item["id"], timestamp))
    if len(events) < 100:
        cli.error("Not enough valid independent listens in dump")
    # Vocabulary is selected from the TRAIN period only, preventing future popularity leakage.
    initial_train, _, cutoff = temporal_split(events)
    support = defaultdict(set)
    for user, item, _ in initial_train:
        support[item].add(user)
    selected = set(sorted((key for key in support if len(support[key]) >= 3), key=lambda key: (-len(support[key]), key))[:args.max_items])
    profiles = defaultdict(set)
    for user, item, _ in initial_train:
        if item in selected:
            profiles[user].add(item)
    # Deterministic hash sampling, not "most active listener" sampling.
    users = set(sorted(user for user, items in profiles.items() if len(items) >= args.min_items_per_user)[:args.max_users])
    events = sorted(set(row for row in events if row[0] in users and row[1] in selected), key=lambda row: row[2])
    train, test = [row for row in events if row[2] < cutoff], [row for row in events if row[2] >= cutoff]
    if not train or not test:
        cli.error("No usable chronological train/test split; choose a larger dump/window")
    baseline = fit(train)
    content_graph = fit_content([metadata[key] for key in sorted(baseline["neighbors"])])
    baseline["content_neighbors"] = content_graph
    baseline_result = evaluate(baseline, train, test)
    tuning = tune_hybrid(train, {key: row for key, row in metadata.items() if metadata_time[key] < cutoff})
    selection = tuning["selected"]
    evaluation_model = {**fit(train, **selection["fit"]), "content_neighbors": content_graph,
                        "hybrid_cf_weight": selection["hybrid_cf_weight"]}
    report = evaluate(evaluation_model, train, test, normalize_candidates=True)
    # Refit serving graph on the full selected sample AFTER measuring held-out quality.
    model = fit(events, **selection["fit"])
    digest = hashlib.sha256()
    with args.dump.open("rb") as file:
        for chunk in iter(lambda: file.read(1024*1024), b""):
            digest.update(chunk)
    manifest = {"dataset": "ListenBrainz official incremental dump", "license": "CC0-1.0",
                "source_url": args.source_url, "sha256": digest.hexdigest(),
                "trained_at": datetime.now(timezone.utc).isoformat(), "since": args.since,
                "raw_listens": raw, "selected_listens": len(events), "users": len(users), "items": len(model["neighbors"]),
                "train_events": len(train), "test_events": len(test), "cutoff_utc": datetime.fromtimestamp(cutoff, timezone.utc).isoformat(),
                "selection": "Train-only top recordings (>=3 listeners), deterministic hashed user sample; identified Spotify submissions excluded",
                "parameters": {**selection["fit"], "min_pair_users": 2, "weight": "log1p(play_count)",
                               "hybrid_cf_weight": selection["hybrid_cf_weight"]},
                "validation": tuning,
                "baseline_on_same_test": baseline_result,
                "evaluation": report,
                "limitations": ["Small non-representative sample; language/genre coverage is not guaranteed", "Metadata is community supplied", "Unknown users/items need a cold-start fallback", "Not a model trained on this app's Spotify history"]}
    if args.evaluate_catalog_expansion:
        manifest["catalog_expansion"] = evaluate_catalog_expansion(train, test, metadata, selection)
    artifact = {"version": 1, "algorithm": "item-knn-cosine", "manifest": manifest,
                "methods": ["item_knn", "content_based", "hybrid"], "content_neighbors": content_graph,
                "hybrid_cf_weight": selection["hybrid_cf_weight"],
                "items": [metadata[key] for key in sorted(model["neighbors"])], **model}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(args.output)
    report_path = args.output.with_name("evaluation.json")
    report_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
