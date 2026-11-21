# Music Discovery Vietnam — bản nâng cấp 2026-11-13

> Cập nhật nhận diện 2026-11-14: xem [CHAY_NHAN_DIEN_FINGERPRINT.md](CHAY_NHAN_DIEN_FINGERPRINT.md).
> Hiện ưu tiên thuật toán nội bộ trước AcoustID trong chế độ hybrid; có thể chọn landmark để chỉ dùng thuật toán dự án.

## 1. Các phần đã sửa

- `POST /api/identify`: file do micro, upload hoặc chia sẻ tab tự nguyện được kiểm tra và giải mã bằng FFprobe/FFmpeg thành PCM WAV 11.025 kHz. MIME/đuôi file chỉ là kiểm tra đầu tiên; nội dung audio mới quyết định khả năng xử lý.
- Chromaprint + AcoustID vẫn là nguồn nhận diện chính khi đã cấu hình.
- Khi API không có kết quả, lỗi hoặc chưa có key, backend thử MDVN Landmark v2. Thuật toán dùng FFT, spectral peaks, hash cặp đỉnh và **temporal-offset voting** qua RPC PostgreSQL.
- `GET /api/identify/history` và `GET /api/identify/{uuid}` lưu/đọc metadata kết quả, không lưu file âm thanh.
- `GET /api/spotify/now-playing`: nhận access token Spotify **của chính người dùng** ở header riêng và lấy metadata từ Spotify Web API, không trích xuất audio.
- `/discover`: preference (genres, moods, languages, artists, blocked artists, discovery level), content-based ranking, feedback like/dislike/save/skip, tương tự bài hát theo tag. Không dùng dữ liệu nghe Spotify để tạo mô hình.
- `ad_campaigns`, `ad_creatives`, `ad_placements`: schema **chưa bật** quảng cáo, không có route phân phối, không có tích hợp player.

## 2. Cài đặt trên máy phát triển

Backend (Python 3.11+):
```bash
cd backend
python -m venv .venv
# Kích hoạt .venv theo hệ điều hành
pip install -r requirements.txt
# Cài FFmpeg và FFprobe bằng package manager của hệ điều hành, kiểm tra:
ffmpeg -version
ffprobe -version
# Cài Chromaprint CLI (fpcalc) nếu dùng AcoustID:
fpcalc -version
cp .env.example .env.local
python -m uvicorn app.main:app --reload --port 8000
```

Frontend (Node 20+):
```bash
cd frontend
npm ci
cp .env.example .env.local
npm run typecheck
npm run dev
```

Đặt vào `.env.local` các biến từ `.env.example`: SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, ACOUSTID_CLIENT_KEY, CHROMAPRINT_FPCALC_PATH, RECOGNITION_FFMPEG_PATH, RECOGNITION_FFPROBE_PATH và thông tin Spotify. Không thêm Client Secret vào frontend, không commit `.env.local`.

Đăng ký lại Spotify OAuth với scope `user-read-currently-playing` bằng cách ngắt và kết nối lại tài khoản. Now Playing chỉ hoạt động khi Spotify trả về dữ liệu từ tài khoản được cấp phép.

## 3. Migration Supabase — cần thực hiện thủ công

**Sao lưu DB và kiểm tra schema thật trước khi chạy SQL.** Nếu database đã có 3 migration cũ, chỉ chạy bản mới:
- `supabase/migrations/20261113_recognition_recommendations.sql`

Sau đó nạp metadata có nguồn:
- `supabase/seeds/20261113_catalog_musicbrainz.sql` (15 bài hát từ trang release MusicBrainz, tag/mood do biên tập viên tự gán).
- Trong Supabase SQL Editor thực hiện theo thứ tự; không cần tải file audio Spotify.

Nếu database chưa có Phase 2/3, phải kiểm tra/tổ chức migration cũ trước; dự án chứa các schema lịch sử khác nhau, không chạy chồng policy không idempotent trên DB production. Không có kết nối Supabase thật trong môi trường tạo ZIP này nên SQL chưa được thực thi trên tài khoản người dùng.

Bổ sung metadata bằng:
```
DATABASE_URL='postgresql+psycopg...?'  # cần DSN psycopg thuần postgresql:// cho script
python backend/tools/import_catalog_csv.py backend/tools/catalog_template.csv --acknowledge-provenance
```
Template CSV trống, phải điền metadata thực cùng source_url/source_license. Script dùng DSN `postgresql://...` từ biến môi trường DATABASE_URL. Thực thi với quyền quản trị ngoài frontend.

## 4. Tạo fingerprint nội bộ (không áp dụng với Spotify audio)

Fingerprint dự phòng chỉ nhận diện được những bản ghi âm mà chủ dự án có quyền tạo fingerprint và đã tự index.

```
DATABASE_URL='postgresql://USER:PASS@HOST:PORT/DB?sslmode=require' \
 python backend/tools/index_licensed_audio.py \
 --track-id UUID_TRONG_MUSIC_CATALOG --file /path/to/authorized.wav --i-have-rights
```

- Chỉ dùng bản ghi âm bạn có quyền xử lý, không dùng luồng Spotify hay vượt DRM.
- Mỗi lần lập chỉ mục tạo `mdvn-landmark-v2` trên toàn bộ bản ghi tối đa 30 phút.
- AcoustID có kho dữ liệu riêng của bên thứ ba. MDVN Landmark chỉ tra kho độc lập; không thể đảm bảo tìm được bài ngẫu nhiên trong Spotify.
- Score của fingerprint và rank chỉ là điểm nội bộ, chưa được hiệu chỉnh xác suất bằng benchmark thực tế.

## 5. API

- `POST /api/identify`: multipart file, JWT Supabase trong Authorization Bearer.
- `GET /api/identify/history`: lịch sử metadata của chính tài khoản.
- `GET /api/identify/{id}`: một lần nhận diện.
- `GET /api/spotify/now-playing`: Bearer Supabase + `X-Spotify-Access-Token` người nghe.
- `GET /api/recommendations`: lấy gợi ý catalog độc lập.
- `GET/PUT /api/recommendations/preferences`: xem/sửa sở thích.
- `POST /api/recommendations/feedback`: track_id UUID, action like/dislike/save/skip.
- `GET /api/recommendations/similar/{track_id}`: các bài có genre/mood/tag tương tự.

Mọi dữ liệu người dùng mới dùng RLS theo `auth.uid()`. Fingerprint index không có quyền truy cập trực tiếp từ trình duyệt; chỉ RPC giới hạn danh sách hash. Dữ liệu Spotify không dùng làm đầu vào thuật toán recommendation.

## 6. Giới hạn cần xử lý trước production

- Chưa có thông tin kết nối project Supabase của bạn, nên chưa kiểm chứng migration/RLS end-to-end.
- Chưa có audio bản quyền thật để benchmark nhận diện và chưa có phép đo top-1/top-5/false positive; cần tập dữ liệu ghi âm thực tế để hiệu chỉnh ngưỡng.
- Bộ seed gồm 15 bản ghi metadata từ MusicBrainz, không phải catalog lớn, không chứa audio/fingerprint. Tên/artist/album thuộc core metadata CC0; mood/genre do biên tập viên tự gán. Các dữ liệu khác của MusicBrainz có giấy phép khác, cần kiểm tra khi mở rộng.
- Chưa tích hợp ACRCloud vì chưa có API key/quyền dịch vụ; interface fallback nội bộ và AcoustID đã có.
- Chưa có infrastructure quota/rate limiting toàn cụm, monitoring và admin UI; nên bổ sung trước production.
- Không trộn, phân tích, tải, thu hoặc fingerprint Spotify audio. Spotify Now Playing chỉ đọc metadata.
- Advertisement Engine mới có schema và không hoạt động; chèn quảng cáo trong Spotify Streaming App cần kiểm tra và có quyền theo Spotify Developer Policy.
- Tốc độ/độ tin cậy phụ thuộc FFmpeg và môi trường server. Trình duyệt không nào bảo đảm phát/chia sẻ audio từ mọi nguồn.
- Kết quả kiểm thử ghi tại `docs/TEST_RESULTS.md`.

## 7. Khuyến nghị an ninh

Bản ZIP này chủ động loại `.env.local`, cache, node_modules và `.git`. Bản ZIP gốc bạn gửi có chứa cấu hình Spotify Client Secret; hãy xoay vòng các secret đã từng chia sẻ và dùng secret manager cho môi trường production.
