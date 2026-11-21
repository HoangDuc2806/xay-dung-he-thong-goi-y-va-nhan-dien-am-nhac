"""Bounded, resumable evaluation of the existing AudD and AcoustID adapters.

Run from backend: python -m tools.evaluate_cloud_recognition --output artifacts/cloud_evaluation --run
Without --run, only validate inputs and print the request budget. Never infer cloud
catalog membership from the local benchmark's reference/unknown roles.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import time
import unicodedata

import numpy as np

from app.core.config import Settings
from app.services.audd_recognition import recognize_audd
from app.services.music_recognition import generate_fingerprint, lookup_acoustid, parse_acoustid_matches
from app.services.mfcc_dtw import read_pcm
from tools.evaluate_recognition import write_wav

PROTOCOL = "cloud-v1-12s-offset20-clean-noise10db-seed20261121"


def normalized(value):
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())


def classify(matches, title, artist):
    if not matches:
        return "not_found"
    first = matches[0]
    artists = {normalized(value) for value in first.get("artists", [])}
    if normalized(first.get("title", "")) == normalized(title) and normalized(artist) in artists:
        return "metadata_match"
    # Different spelling, versions, credits, or an incorrect match require review.
    return "needs_review"


def summarize(rows):
    counts = Counter(row["status"] for row in rows)
    completed = [row for row in rows if row["status"] in {"metadata_match", "not_found", "needs_review"}]
    times = [row["elapsed_ms"] for row in completed]
    return {
        "attempted": len(rows), "completed": len(completed),
        "metadata_match": counts["metadata_match"], "not_found": counts["not_found"],
        "needs_review": counts["needs_review"], "errors": counts["error"],
        "interrupted": counts["started"],
        "metadata_match_percent_completed": round(100 * counts["metadata_match"] / len(completed), 2) if completed else None,
        "latency_p50_ms": round(float(np.percentile(times, 50)), 2) if times else None,
        "latency_p95_ms": round(float(np.percentile(times, 95)), 2) if times else None,
    }


def save_report(output, rows, planned, stopped):
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "protocol": PROTOCOL,
        "planned_requests_per_provider": planned, "stopped": stopped,
        "summary": {provider: summarize([r for r in rows if r["provider"] == provider]) for provider in ("audd", "acoustid")},
        "conditions": {provider: {condition: summarize([r for r in rows if r["provider"] == provider and r["condition"] == condition])
                                 for condition in ("clean", "noise_10db")} for provider in ("audd", "acoustid")},
        "limitations": [
            "Small open-licensed catalog; not representative of Spotify or Vietnamese popular music.",
            "12-second digital excerpts at 11025 Hz, not physical microphone recordings or full original files.",
            "Cloud catalog membership is unknown; not_found does not prove absence from the provider catalog.",
            "Automated title-and-artist agreement is not verification of the exact recording/version.",
            "Unmatched returned metadata needs human review; API errors are not recognition misses.",
            "Latency includes adapter processing and network, excludes web authentication, upload and clip creation.",
        ], "recordings": rows,
    }
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    esc = lambda v: html.escape(str(v))
    headers = ["Dịch vụ", "Hoàn thành", "Khớp tên + nghệ sĩ", "Không tìm thấy", "Cần đối chiếu", "Lỗi", "Khớp (%)", "p50 (ms)"]
    summary_rows = []
    for provider, value in report["summary"].items():
        summary_rows.append([provider, value["completed"], value["metadata_match"], value["not_found"], value["needs_review"], value["errors"], value["metadata_match_percent_completed"], value["latency_p50_ms"]])
    def table(head, values):
        return '<div class="scroll"><table><tr>' + ''.join('<th>'+esc(h)+'</th>' for h in head) + '</tr>' + ''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in values) + '</table></div>'
    details = [[r["provider"], r["expected_title"], r["expected_artist"], r["condition"], r["status"],
                ' | '.join(m.get("title", "")+' — '+', '.join(m.get("artists", [])) for m in r.get("matches", [])[:1]),
                r.get("error_type", "")] for r in rows]
    document = '''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Đánh giá AudD và AcoustID</title><style>body{font:16px/1.6 system-ui;max-width:1250px;margin:40px auto;padding:0 20px;color:#192135}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #ccd3de;padding:10px;text-align:left}th{background:#eeeafa}.scroll{overflow:auto}aside{background:#fff2d4;padding:16px;margin:20px 0}h1{line-height:1.2}</style>
<h1>Đánh giá AudD và AcoustID</h1><p>13 bản nhạc có nhãn từ Wikimedia Commons, mỗi bài có đoạn sạch và đoạn nhiễu 10 dB. Cùng đoạn 12 giây bắt đầu tại giây 20 được gửi đến hai dịch vụ. Âm thanh mono PCM16 11025 Hz. Chỉ gọi adapter dịch vụ; không thay chế độ nhận diện của web.</p>
<aside>Đây là kiểm thử sơ bộ trên đoạn âm thanh số. Không phải 26 bài khác nhau và không phải đánh giá thu micro thực tế. Tỷ lệ khớp chỉ đo tên bài và nghệ sĩ đã chuẩn hóa; khác phiên bản bản thu vẫn có thể cùng tên. Kết quả cần đối chiếu chưa được tính là đúng hoặc kết luận sai. Lỗi dịch vụ tách khỏi trường hợp không tìm thấy.</aside>'''
    document += '<p>Thời điểm UTC: '+esc(report['generated_at'])+'</p>'
    document += table(headers, summary_rows)
    document += '<p>Tỷ lệ khớp = số đoạn khớp tên và nghệ sĩ / số yêu cầu hoàn thành hợp lệ. Xem thêm số lỗi để tránh hiểu sai tỷ lệ này.</p>'
    document += '<h2>Chi tiết từng đoạn</h2>'+table(["Dịch vụ", "Bài đúng", "Nghệ sĩ đúng", "Điều kiện", "Kết quả", "Kết quả đầu tiên trả về", "Lỗi"], details)
    document += '<p><a href="results.json">Toàn bộ dữ liệu và kết quả theo điều kiện</a> · <a href="journal.jsonl">Nhật ký từng lượt</a></p>'
    document += '<p>Không tìm thấy có thể do đoạn âm thanh, định dạng fingerprint hoặc độ bao phủ dịch vụ; không đủ để kết luận bài không có trong kho. AcoustID được thử theo cách tích hợp hiện tại của ứng dụng, không phải phép đo tối ưu trên file bài hát đầy đủ.</p>'
    document += '<p>Tài liệu: <a href="https://docs.audd.io/">AudD</a> · <a href="https://acoustid.org/webservice">AcoustID</a></p></html>'
    (output / "report.html").write_text(document, encoding="utf-8")
    return report


async def evaluate(args):
    settings = Settings()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    source = args.manifest.parent.resolve()
    tracks = manifest["tracks"]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    journal = output / "journal.jsonl"
    previous = {}
    if journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            previous[row["request_id"]] = row
    clips = []
    for index, track in enumerate(tracks):
        path = (source / track["file"]).resolve()
        if not path.is_relative_to(source) or not track.get("license") or not track.get("title") or not track.get("artist"):
            raise ValueError("Invalid labeled source or provenance")
        samples = read_pcm(path)
        original = samples[20*11025:32*11025]
        if len(original) != 12*11025:
            raise ValueError("Each recording needs at least 32 seconds")
        for condition in ("clean", "noise_10db"):
            query = original.copy()
            if condition == "noise_10db":
                rms = float(np.sqrt(np.mean(query * query)))
                query += np.random.default_rng(20261121+index).normal(0, rms / np.sqrt(10), len(query))
            path = output / f"clip-{index}-{condition}.wav"
            write_wav(path, query)
            clips.append((track, condition, path, hashlib.sha256(path.read_bytes()).hexdigest()))
    print(json.dumps({"tracks":len(tracks), "requests_per_provider":len(clips),
                      "audd_configured":bool(settings.audd_api_token.strip()),
                      "acoustid_configured":bool(settings.acoustid_client_key.strip())}), flush=True)
    if not args.run:
        return
    if not settings.audd_api_token.strip() or not settings.acoustid_client_key.strip():
        raise ValueError("Both provider credentials must be configured; values are never printed")
    # Fail locally before consuming API quota if fpcalc cannot process the test WAV.
    await generate_fingerprint(clips[0][2], fpcalc_path=settings.chromaprint_fpcalc_path)
    stopped = {}
    errors = Counter()
    rows = []
    def append(row):
        with journal.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
    for track, condition, path, digest in clips:
        for provider in ("audd", "acoustid"):
            request_id = hashlib.sha256(f'{PROTOCOL}|{provider}|{digest}|{track["title"]}|{track["artist"]}'.encode()).hexdigest()
            if request_id in previous:
                rows.append(previous[request_id])
                continue
            if provider in stopped:
                continue
            row = {"request_id":request_id, "provider":provider, "track_id":track["id"],
                   "expected_title":track["title"], "expected_artist":track["artist"],
                   "source_url":track["source_url"], "condition":condition, "clip_sha256":digest,
                   "status":"started", "started_at":datetime.now(timezone.utc).isoformat()}
            append(row)  # Resume never re-sends an interrupted, potentially billable request.
            start = time.perf_counter()
            try:
                if provider == "audd":
                    matches = await recognize_audd(path, settings.audd_api_token)
                else:
                    duration, fingerprint = await generate_fingerprint(path, fpcalc_path=settings.chromaprint_fpcalc_path)
                    matches = parse_acoustid_matches(await lookup_acoustid(settings.acoustid_client_key, fingerprint, duration))
                row.update(status=classify(matches, track["title"], track["artist"]), matches=matches)
                errors[provider] = 0
            except Exception as exc:
                # Avoid raw provider errors/URLs/credentials in the report.
                row.update(status="error", error_type=type(exc).__name__, http_status=getattr(exc, "status_code", None))
                errors[provider] += 1
                if errors[provider] >= 2 or getattr(exc, "status_code", None) == 429:
                    stopped[provider] = "Stopped after rate limit or two consecutive errors; no automatic retries"
            row["elapsed_ms"] = round((time.perf_counter()-start)*1000, 3)
            append(row)
            rows.append(row)
            save_report(output, rows, len(clips), stopped)
            print(f'{provider} {track["id"]} {condition}: {row["status"]}', flush=True)
            await asyncio.sleep(0.4)
    result = save_report(output, rows, len(clips), stopped)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/recognition/manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/cloud_evaluation"))
    parser.add_argument("--run", action="store_true", help="Send real API requests using configured credentials")
    asyncio.run(evaluate(parser.parse_args()))


if __name__ == "__main__":
    main()
