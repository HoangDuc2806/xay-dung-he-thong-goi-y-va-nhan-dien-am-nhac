# Mở rộng gợi ý và nhận diện — 21/11/2026

- Thử nghiệm loại cố định 395/2.000 mã bài rồi bổ sung lại dưới dạng bài chỉ có metadata. Trên cùng 1.154 người dùng test, Recall@10 Hybrid tăng từ 12,39% lên 13,29% và NDCG@10 từ 0,1026 lên 0,1066. Kết quả đánh giá giả định metadata đã có sẵn.
- Kho nhận diện có 10 bài tham chiếu từ bộ 13 bản ghi Wikimedia Commons, tối đa 120 giây/bản. Trên 176 đoạn thử mỗi phương pháp, Landmark đúng 158/176 và MFCC + DTW đúng 98/176. Cả hai nhận nhầm 10/32 đoạn ngoài kho.
- Cùng một đoạn WAV bắt đầu ở giây 72 của *The Entertainer* được gửi đến API so sánh. Cả Landmark và MFCC + DTW trả đúng bản tham chiếu. Chế độ so sánh trên web và công cụ tổng hợp WAV có nhãn đã sẵn sàng cho bộ đo micro thực tế.

# Tối ưu gợi ý và nhận diện — 20/11/2026

Tập ListenBrainz dùng 2.000 bài và 1.154 người đủ điều kiện trên test. Chọn cấu hình bằng NDCG@10 trên phần cuối của train, sau đó đo baseline và cấu hình đã chọn trên cùng test. Cấu hình phục vụ tăng từ 50 lên 100 hàng xóm, giảm hệ số shrinkage từ 10 xuống 5 và giảm ảnh hưởng của người nghe quá nhiều bài. Hybrid dùng 70% điểm cộng tác và 30% điểm nội dung sau khi lọc ứng viên.

| Chỉ số Hybrid | Baseline trong lần chạy này | Bản tối ưu |
|---|---:|---:|
| Recall@10 | 14,49% | 14,79% |
| NDCG@10 | 0,1170 | 0,1192 |
| Precision@10 | 5,53% | 5,48% |
| Độ phủ catalog | 69,25% | 71,10% |

Đo riêng hàm xếp hạng với catalog từ artifact và sở thích B-Ray. Lần đầu sau khi nạp model giảm từ khoảng 1.517 ms xuống 59 ms nhờ chỉ mục TF-IDF thưa và tính tương đồng theo bài làm mẫu. Các lần tiếp theo của bản mới có trung vị khoảng 13 ms. Phép đo này chưa tính đọc dữ liệu, xác thực hoặc hiển thị trang. API thử với dữ liệu B-Ray đã lưu trả 16 bài. Nếu hàng xóm của mô hình bị loại bởi bộ lọc, kết quả có thể dùng bài phù hợp theo metadata và phản hồi.

Landmark dùng chỉ mục fingerprint đã nạp sẵn, tái sử dụng hash cặp đỉnh và đếm phiếu một lượt. Thử 400, 700, 1.000 và 1.600 hash trên tập hiệu chỉnh có thêm nhiễu 0 dB. Chọn 700 vì đạt điểm tốt nhất trên tập hiệu chỉnh với ít hash nhất trong nhóm đồng điểm. MFCC + DTW tái sử dụng bộ nhớ cho các hàng chi phí. Thử khử nhiễu MFCC cho recall hiệu chỉnh kém hơn nên giữ biểu diễn gốc.

| Chỉ số nhận diện nội bộ | Trước | Sau |
|---|---:|---:|
| Landmark Top-1, gồm từ chối đúng bài ngoài kho | 49/56 | 50/56 |
| Landmark nhận đúng bài có trong kho | 41/48 | 42/48 |
| Landmark nhận nhầm bài ngoài kho | 0/8 | 0/8 |
| Landmark thời gian xử lý trung vị | 200,654 ms | 46,249 ms |
| MFCC + DTW Top-1 | 32/56 | 32/56 |
| MFCC + DTW thời gian xử lý trung vị | 21,312 ms | 19,817 ms |

Phần nhận diện dùng sáu bản tham chiếu, đoạn thử cắt từ audio và nhiễu mô phỏng. So sánh với cùng 56 đoạn đã dùng trong báo cáo trước. Bản thu micro thực tế và tỷ lệ khớp của AudD chưa được đo trong đợt này. Nhánh AudD chọn cửa sổ 12 giây có tín hiệu liên tục trong phần đầu bản thu và báo khi đầu vào gần như im lặng. Hợp đồng gửi audio được test bằng dịch vụ giả lập.

Backend đạt **148 test**, bỏ qua 9 test phụ thuộc FFmpeg. Cả hai API nhận diện nội bộ trả đúng `Tranquility` từ đoạn CC BY, với xác thực thử. Kết quả và cấu hình trong `backend/artifacts/evaluation.json` và `backend/artifacts/recognition_evaluation.json`. Có thể chạy lại nhận diện bằng `python -m tools.evaluate_recognition --hard-calibration --landmark-query-points 700` từ `backend`. Nếu dùng bộ dữ liệu khác, chạy lại hiệu chỉnh để chọn ngưỡng và số hash.

# 2026-11-20 — artist cold start and recommendation UI

- Backend **145 passed, 9 skipped**; frontend typecheck passed and Vitest **27 passed**. Historical FFmpeg skips and Starlette/httpx warning remain.
- Hidden algorithm selector/internal scores in the product page; requests use Hybrid explicitly. Research API retains method selection.
- Regression cases cover artist collaboration credits, favorite seeds vs actual listening, new recordings outside the collaborative vocabulary, missing vs conflicting labels, negative feedback and duplicate recordings.
- Built 142 source-verified MusicBrainz core metadata rows; imported 136 new rows after existing-title/artist checks. Live database now has **2,159 active songs**, including **16 B-Ray credits**. Authenticated role read verified; no schema/RLS changes.
- Actual B-Ray source rows + existing model catalog through the HTTP route (auth fixture) returned **200 / 16 recommendations**, including Do for Love, Chờ Anh Về, Ex's Hate Me. No fake co-listening counts: new tracks use content signals.
- Local `/discover` returned **HTTP 200**. Interactive signed-in browser flow not verified in this update. No new aggregate accuracy claim; historical offline metrics remain scoped to their earlier dataset/protocol.
- Details and reproduction: [SUA_GOI_Y_NGHE_SI_20261120.md](SUA_GOI_Y_NGHE_SI_20261120.md).

# 2026-11-19 — algorithm comparison requirements

- Backend full suite: **139 passed, 9 skipped** (FFmpeg-dependent historical codec cases), one existing Starlette/httpx deprecation warning.
- Frontend `npm run typecheck` passed; Vitest **27 passed**. No live interactive browser verification or production deployment in this update.
- Added real metadata TF-IDF/cosine Content-based and fixed 70/30 Hybrid alongside Item-KNN; same chronological protocol and 1,154 test users. Recall@10: Content **0.127798**, CF **0.139730**, Hybrid **0.144990**, Popularity **0.016371**. Earliest metadata is retained to avoid future labels.
- Added independent MFCC/subsequence-DTW matcher and authenticated short-WAV local API; both local matchers use an attributed 6-track reference bundle.
- Downloaded 8 real CC-BY 3.0 recordings via Wikimedia license metadata. Six references, distinct calibration-unknown/test-unknown tracks, non-overlapping 8-second windows, fixed seed, thresholds selected only on calibration. No AudD requests used for this study.
- Each recognition method: **56 test queries (48 known / 8 unknown)**. Landmark accuracy **0.875**, known recall **41/48**, unknown FAR **0/8**; MFCC-DTW accuracy **0.571429**, known recall **26/48**, unknown FAR **2/8**. Controlled digital distortions only; physical microphone/room/genre coverage is unverified.
- Actual extraction + HTTP route smoke check with real CC-BY audio returned **200 / matched / Tranquility** for both methods; only authentication replaced by a fixture. This is not a live logged-in browser run.
- Detailed reports: [algorithm study](BAO_CAO_NGHIEN_CUU_THUAT_TOAN.md), [requirements matrix and reproduction](DOI_CHIEU_YEU_CAU_GIANG_VIEN.md). Raw metrics/provenance under `backend/artifacts/`; raw audio ignored under `backend/data/`.
- No database schema/RLS changes or remote deployment in this update.

# 2026-11-14 — trained ListenBrainz recommendations

- Backend full suite: **132 passed, 9 skipped**. Skips remain the FFmpeg-dependent recognition cases. One existing Starlette/httpx deprecation warning.
- Frontend: `npm run typecheck` passed; Vitest **26 passed**.
- Real CC0 dump SHA256 verified against the official checksum. Trained serving graph: **167,468 events, 3,283 users, 2,000 recordings**, top 50 neighbours, log-count cosine and support shrinkage.
- Global chronological evaluation: 144,628 train events / 22,840 test events, 1,154 evaluated users. Item-KNN Recall@10 **0.139730**, popularity **0.016371**; NDCG@10 **0.114844** vs **0.019857**. Vocabulary/user selection is train-only. This is a filtered sample benchmark, not Spotify or Vietnamese music accuracy.
- Actual Supabase import verified: **2,000** learned metadata rows, **2,023** total active rows; authenticated database role can read all 2,023 active rows under existing RLS. No schema or RLS changes.
- Real artifact inference verified: a positive seed produced 14 eligible item-KNN recommendations. HTTP integration tests separately verify ownership filters and learned ranking via dependency fixtures.
- Local Next `/discover`: HTTP **200**. Interactive browser flow, real ListenBrainz account history and production build are not verified by this update. No Spotify history is used to train or rank.
- Reproduction/limits: [GOI_Y_HOC_TU_LUOT_NGHE.md](GOI_Y_HOC_TU_LUOT_NGHE.md), machine-readable report: `backend/artifacts/evaluation.json`.

# Verification results — 2026-11-13

## Re-run on Windows — 2026-11-14

### Recommendation coverage and interface refinements (latest)

- Initial connected Supabase read-only verification found **15 tracks, 0 Vietnamese tracks and 0 tracks tagged sad**. A no-match for sad + vi must not be displayed as an empty catalog.
- Backend distinguishes `empty_catalog`, `no_matches`, `personalized`, and `discovery`; exposes available metadata and missing artists. Selected genres/moods/languages filter candidates before ranking. Zero-score unrelated tracks are omitted when personal preferences are present.
- Artist comparison handles spacing/punctuation/diacritics (for example bray / B-Ray) without substring matching. The diversity slider limits repeated artists rather than giving all tracks an arbitrary score bonus.
- Explicit Browse Catalog mode retains saved preferences and respects hidden artists and negative feedback; results are clearly labeled as general catalog browsing.
- Discovery UI has collapsible preferences, separate save/load errors, a direct Spotify search, honest empty-state messages and loading states for similar tracks. Home banners are shorter and secondary text has higher contrast.
- Added eight Vietnamese metadata records using `supabase/seeds/20261114_vietnamese_recommendation_metadata.sql`. Titles/artists/years were checked against the MusicBrainz WM Vietnam release listing; genre/mood labels are editorial examples. No audio or Spotify analytics were imported.
- Post-insert connected SQL verification: **23 active tracks, 8 Vietnamese tracks, 6 Vietnamese tracks tagged sad**. No schema or private preference data was changed.
- Backend: **123 passed, 9 skipped**. Frontend: TypeScript passed, **25 tests passed**. The localhost /discover route returned HTTP 200 with the new page title.
- A real authenticated browser save/feedback round-trip has not been automated.

### Homepage pagination and preference save fix (latest)

- Backend: **115 passed, 9 skipped**. Frontend: TypeScript passed; **22 tests passed**.
- Fixed preference GET -> form -> PUT round-trip: ownership fields are omitted from editable responses and explicitly excluded from frontend payloads. Client-supplied user_id remains rejected.
- Homepage loads up to three ten-item Spotify search pages initially, with further batches through Load More. Pages are deduplicated by Spotify track ID; partial loads retain successful pages and a retry offset.
- Live localhost API probes at offsets 0, 10 and 20 each returned ten items and advancing next offsets. No live Supabase preference update was performed; ownership and round-trip behavior are covered using dependency mocks.
- No database migration or app packaging/native conversion was performed.

### AudD microphone integration (latest)

- Backend: **109 passed, 9 skipped**; the skipped cases still require FFmpeg/FFprobe.
- Provider tests cover multipart upload, no-match, token/quota errors, timeout, WAV validation/clipping and HTTP recognition/history without FFmpeg or a local fingerprint catalog.
- Automated provider tests use mocked HTTP responses. A user-supplied screenshot on 2026-11-14 shows a recorded WAV and an actual AudD result: “Quá Đủ Rồi” — CoolKid, with a Spotify link. This confirms a live result was returned; the source audio and correctness have not been independently checked.
- Frontend: TypeScript passed; **16 tests passed**, including PCM WAV header/sample encoding.
- Browser recording/WAV preview and the returned AudD result are visible in the user screenshot. This is one observed example, not an accuracy or reliability benchmark.
- No migration is needed for AudD mode; recognition result metadata is stored in the existing JSON history field.

### Local landmark integration

- Backend after recognition changes: `python -m pytest -q`: **95 passed, 9 skipped**.
- Nine skipped cases require FFmpeg/FFprobe (7 codec cases, invalid-media decode, HTTP WebM decode).
- Actual spectral extraction/voting passes synthetic excerpts with unaligned offsets, noise and gain change; silence, unrelated noise and duplicate-hash vote inflation are covered.
- HTTP landmark tests use real extraction and an in-memory RPC substitute; decode is substituted with a copy of already normalized PCM. This is not live PostgreSQL/Supabase verification.
- CLI import/usage checks pass from another working directory for the exporter, indexer and local evaluator.
- Frontend: `npm run typecheck` passed; `npm test -- --reporter=dot`: **14 passed**.
- Live Supabase matching, real microphone audio and recognition accuracy on actual music: **not verified**. No audio reference collection was provided or indexed by this change.
- No production build or remote schema change was performed in this update.
- The historical results below describe an earlier environment; the re-run above is the current result.

## Historical results

- Backend: `python -m pytest -q`: **84 passed**.
- All original 68 tests pass after adapting the mocked-fake-audio tests to the FFmpeg decode-first pipeline.
- New tests cover actual WAV/MP3/WebM-Opus/Ogg/FLAC/M4A/AIFF FFmpeg decode, invalid file rejection, offset-voting fingerprint matching, HTTP WebM recognition, preference ranking, feedback, similar-song ranking, RLS route ownership via dependency mocks, and Spotify Now Playing via mocked Spotify API.
- Frontend: `tsc --noEmit --pretty false --incremental false`: **passed**.
- Next.js production build: **NOT VERIFIED**. Build could not download `@next/swc-linux-x64-gnu` from npm registry (network `EAI_AGAIN`); bundled SWC binary in original ZIP is Windows-only. Do not interpret this as a successful production build.
- Frontend Vitest test execution: **not verified** due native Rollup/ESBuild platform dependency in Windows ZIP; run `npm ci && npm test` on developer machine.
- PostgreSQL migration SQL: **not executed on live Supabase**. Test with a database backup first.
- Recognition against real licensed recordings: **not tested**; no benchmark collection or audio catalog was supplied.
- Spotify OAuth and user Now Playing: test uses mocked API response; **not tested with a real Spotify account**.
- Seed: 15 metadata entries, with 4 MusicBrainz release citations. Audio and fingerprints are intentionally absent.
- No commercial ad serving or audio advertising has been enabled.
