# Music Discovery Vietnam – triển khai module nhận diện, gợi ý và quảng cáo

## Đã triển khai trong source

1. **Recognition fallback:** giữ Chromaprint + AcoustID làm luồng chính. Khi thiếu `fpcalc`, AcoustID lỗi hoặc không có kết quả, backend thử fingerprint dự phòng `mdvn-landmark-v1` bằng FFmpeg + NumPy và so khớp với `music_catalog.fingerprint_hashes`.
2. **Recommendation:** thêm API `/api/recommendations`, `/api/recommendations/preferences` và trang Discover. Thuật toán chỉ dùng metadata catalog độc lập (genre, mood, language) cùng sở thích người dùng khai báo. Không đọc lịch sử nghe Spotify, Spotify popularity hoặc Spotify audio features.
3. **Advertisement foundation:** thêm schema campaign/creative/placement ở trạng thái draft/disabled. Không có ad-serving endpoint, không chèn quảng cáo vào Spotify Player và không bật phân phối quảng cáo.

## Cài đặt

- Cài `fpcalc` (Chromaprint) và `ffmpeg` trên backend. Fingerprint dự phòng cần thêm `numpy` từ `backend/requirements.txt`.
- Chạy migration `supabase/migrations/20261107_discovery_recommendations_ads_foundation.sql` trong Supabase SQL Editor sau khi kiểm tra schema hiện tại.
- Khởi động backend và frontend như README.

## Nạp catalog độc lập

Thêm metadata vào `public.music_catalog`: title, artist, genres, moods, language, spotify_search_query, source và source_url. Chỉ dùng metadata có nguồn/quyền sử dụng hợp lệ. `spotify_search_query` là chuỗi tìm kiếm do biên tập viên tạo, không phải dữ liệu phân tích Spotify.

Để fingerprint một bản ghi âm được cấp phép, chạy:

```bash
cd backend
python scripts_fingerprint_catalog.py /path/to/licensed-audio-file.mp3
```

Lấy mảng `hashes[].hash` từ JSON kết quả và lưu vào `music_catalog.fingerprint_hashes`. Fingerprint dự phòng chỉ so khớp với catalog đã được fingerprint bằng cùng phiên bản thuật toán; nó không phải fingerprint AcoustID và không thể nhận diện toàn bộ bài hát trên Internet.

## Giới hạn và lưu ý

- Fingerprint landmark là phương án dự phòng cho catalog nội bộ, không thay thế AcoustID/MusicBrainz.
- `match_score` của fingerprint là điểm tương đồng thô, không phải xác suất nhận diện.
- Trang Discover hiện yêu cầu catalog có dữ liệu. Migration không tự tạo dữ liệu nhạc mẫu.
- Advertisement tables chỉ là khung quản trị tương lai. Chưa có quảng cáo trong giao diện, player hoặc API.
- Trước khi phát hành thương mại, cần rà soát điều khoản Spotify Developer Policy và xin phê duyệt phù hợp cho mô hình ứng dụng.

## API mới

- `GET /api/recommendations`: yêu cầu Bearer token; trả catalog đã xếp hạng.
- `GET /api/recommendations/preferences`: đọc sở thích tài khoản hiện tại.
- `PUT /api/recommendations/preferences`: lưu genres/moods/languages cho tài khoản hiện tại.
- `POST /api/identify`: giữ nguyên endpoint hiện tại; response có thêm `recognition_method` để phân biệt `chromaprint_acoustid` và `mdvn_landmark`.

Trọng số ranking ban đầu: genre 55%, mood 35%, language 10%. Đây là heuristic có thể điều chỉnh bằng đánh giá người dùng, không phải mô hình học máy đã huấn luyện.
