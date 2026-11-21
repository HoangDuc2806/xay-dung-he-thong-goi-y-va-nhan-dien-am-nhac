"""Calibrate on separate excerpts, then evaluate both local music matchers.

Uses real open-licensed recordings with controlled distortions, not a physical
microphone benchmark. The two unknown songs are disjoint between calibration/test.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
import wave
import numpy as np
from app.services.landmark_fingerprint import fingerprint_wav
from app.services.local_recognition import candidates, load_references
from app.services.mfcc_dtw import mfcc_features, read_pcm


def write_wav(path, samples):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(11025)
        audio.writeframes(np.clip(samples*32768, -32768, 32767).astype("<i2").tobytes())


def choose_threshold(rows):
    qualities = sorted({row["score"] for row in rows})
    thresholds = [0.000001, 1.000001] + [(left+right)/2 for left,right in zip(qualities, qualities[1:]) if right > 0]
    def objective(threshold):
        positive = [row for row in rows if row["expected"] is not None]
        negative = [row for row in rows if row["expected"] is None]
        recall = sum(row["predicted"] == row["expected"] and row["score"] >= threshold for row in positive)/max(1,len(positive))
        rejection = sum(row["score"] < threshold for row in negative)/max(1,len(negative))
        return ((recall+rejection)/2, rejection, threshold)
    return max(thresholds, key=objective)


def summarize(rows):
    total = len(rows)
    known = [row for row in rows if row["expected"] is not None]
    unknown = [row for row in rows if row["expected"] is None]
    tp = sum(row["predicted"] == row["expected"] for row in known)
    fp = sum(row["predicted"] is not None and row["predicted"] != row["expected"] for row in rows)
    false_unknown = sum(row["predicted"] is not None for row in unknown)
    return {"queries": total, "known_queries":len(known), "unknown_queries":len(unknown),
            "top1_accuracy": round(sum(row["predicted"]==row["expected"] for row in rows)/max(1,total),6),
            "known_recall":round(tp/max(1,len(known)),6), "precision":round(tp/max(1,tp+fp),6),
            "unknown_false_accept_rate":round(false_unknown/max(1,len(unknown)),6),
            "latency_ms_p50":round(float(np.percentile([row["elapsed_ms"] for row in rows],50)),3),
            "latency_ms_p95":round(float(np.percentile([row["elapsed_ms"] for row in rows],95)),3)}


def query_windows(duration, split):
    if split == "calibration":
        return [("calibration", 3.137)]
    windows = [("early", 20.319), ("early", 30.173)]
    middle, late = max(60.4, duration * 0.6), duration - 8.25
    if middle + 8 <= duration and late - middle >= 8:
        windows.append(("middle", middle))
    if late >= 60:
        windows.append(("late", late))
    return windows


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--manifest",type=Path,default=Path("data/recognition/manifest.json"))
    cli.add_argument("--output",type=Path,default=Path("artifacts/recognition_evaluation.json"))
    cli.add_argument("--bundle",type=Path,default=Path("artifacts/local_recognition.npz"))
    cli.add_argument("--landmark-query-points", type=int, default=700, choices=(400, 700, 1000, 1600))
    cli.add_argument("--hard-calibration", action="store_true", help="Include 0 dB noise in calibration, using a separate random stream")
    args=cli.parse_args()
    tracks=json.loads(args.manifest.read_text(encoding="utf-8"))["tracks"]
    source=args.manifest.parent.resolve()
    for track in tracks:
        path=(source/track["file"]).resolve()
        if not path.is_relative_to(source) or not track.get("license") or not track.get("source_url","").startswith("https://"):
            cli.error("Invalid reference provenance/path")
        track["samples"]=read_pcm(path)
    references=[track for track in tracks if track["role"]=="reference"]
    if len(references)<2 or not any(track["role"]=="calibration_unknown" for track in tracks) or not any(track["role"]=="test_unknown" for track in tracks):
        cli.error("Need at least 2 references and separate unknown calibration/test recordings")
    bundle={}
    public=[]
    started=time.perf_counter()
    for index,track in enumerate(references):
        points=fingerprint_wav(source/track["file"],max_points=200000)
        bundle[f"hashes_{index}"]=np.array([value[0] for value in points],dtype="U16")
        bundle[f"offsets_{index}"]=np.array([value[1] for value in points],dtype=np.int32)
        bundle[f"mfcc_{index}"]=mfcc_features(track["samples"])
        public.append({key:value for key,value in track.items() if key!="samples"})
    bundle["metadata"]=np.array(json.dumps({"version":1,"tracks":public,"landmark_query_points":args.landmark_query_points},ensure_ascii=False))
    target=args.bundle
    target.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(target,**bundle)
    index_seconds=time.perf_counter()-started
    indexed=load_references(str(target))
    rows=[]
    rng=np.random.default_rng(20261119)
    calibration_noise = np.random.default_rng(20261120)
    calibration_conditions = ["clean", "noise_10db"]
    if args.hard_calibration:
        calibration_conditions.append("noise_0db")
    with tempfile.TemporaryDirectory(prefix="mdvn-benchmark-") as temp:
        wav=Path(temp)/"query.wav"
        for split, conditions in [("calibration",calibration_conditions),
                                  ("test",["clean","gain_03","noise_10db","noise_0db"])]:
            for track in tracks:
                if track["role"] not in ("reference",f"{split}_unknown"):
                    continue
                for position, offset in query_windows(len(track["samples"])/11025, split):
                    begin=int(offset*11025)
                    original=track["samples"][begin:begin+8*11025]
                    if len(original)!=8*11025:
                        cli.error("A recording is too short for the declared query protocol")
                    for condition in conditions:
                        query=original.copy()
                        if condition=="gain_03": query*=0.3
                        if condition.startswith("noise_"):
                            snr=10 if condition=="noise_10db" else 0
                            rms=np.sqrt(np.mean(query*query))
                            noise_rng = calibration_noise if split == "calibration" and condition == "noise_0db" else rng
                            query+=noise_rng.normal(0,rms/(10**(snr/20)),len(query))
                        write_wav(wav,query)
                        for method in ("landmark","mfcc_dtw"):
                            started=time.perf_counter()
                            matches=candidates(wav,indexed,method)
                            elapsed=(time.perf_counter()-started)*1000
                            best=matches[0] if matches else {"id":None,"score":0.0}
                            rows.append({"split":split,"method":method,"track":track["id"],"condition":condition,"position":position,"offset_seconds":offset,
                                         "expected":track["id"] if track["role"]=="reference" else None,
                                         "predicted":best["id"],"score":best["score"],"elapsed_ms":elapsed})
    thresholds={method:choose_threshold([row for row in rows if row["method"]==method and row["split"]=="calibration"]) for method in ("landmark","mfcc_dtw")}
    for row in rows:
        if row["score"] < thresholds[row["method"]]: row["predicted"]=None
    results={}
    calibration={}
    for method in thresholds:
        test=[row for row in rows if row["split"]=="test" and row["method"]==method]
        calibration[method]=summarize([row for row in rows if row["split"]=="calibration" and row["method"]==method])
        results[method]={"threshold":thresholds[method],**summarize(test),
                         "conditions":{condition:summarize([row for row in test if row["condition"]==condition]) for condition in sorted({row["condition"] for row in test})},
                         "positions":{position:summarize([row for row in test if row["position"]==position]) for position in sorted({row["position"] for row in test})}}
    max_reference_seconds=max(round(len(track["samples"])/11025,3) for track in references)
    report={"generated_at":datetime.now(timezone.utc).isoformat(),"dataset":f"{len(tracks)} openly licensed recordings from Wikimedia Commons",
            "reference_tracks":len(references),"max_reference_seconds":max_reference_seconds,
            "index_seconds":round(index_seconds,3),"index_bytes":target.stat().st_size,
            "protocol":"8-second excerpts; calibration at 3.137s; disjoint tests at 20.319/30.173s and after 60s when long enough; distinct unknown recordings; seed=20261119",
            "threshold_selection":"Maximize calibration balanced known-recall/unknown-rejection; test never used to select threshold",
            "landmark_query_points":args.landmark_query_points,"calibration_conditions":calibration_conditions,"calibration":calibration,"results":results,"limitations":["Small open catalog; not representative of Spotify or all genres","Controlled digital noise/gain, not physical microphone recordings","No learned neural audio model; MFCC-DTW is a signal-processing baseline",f"References are indexed for at most the first {max_reference_seconds:g} seconds"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    with args.output.with_suffix(".csv").open("w",newline="",encoding="utf-8") as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
