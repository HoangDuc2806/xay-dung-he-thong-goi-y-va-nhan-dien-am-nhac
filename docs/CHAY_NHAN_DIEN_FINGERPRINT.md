# Chạy nhận diện âm nhạc bằng thuật toán fingerprint

## Phạm vi

Thuật toán `mdvn-landmark-v2` trong `backend/app/services/landmark_fingerprint.py`:

1. FFmpeg giải mã MP3/WAV/WebM… thành PCM mono 16-bit, 11025 Hz.
2. STFT dùng cửa sổ Hann 2048 mẫu, bước 512 mẫu.
3. Chọn các đỉnh phổ trong dải khoảng 260–3500 Hz.
4. Ghép cặp đỉnh theo khoảng thời gian, mã hóa tần số và khoảng cách thành hash.
5. So khớp hash trong kho, bỏ phiếu theo độ lệch thời gian (bucket 125 ms).
6. Chỉ giữ kết quả vượt ngưỡng số hash khác nhau và tỷ lệ khớp.

Không có bước huấn luyện mạng neural. Bước chuẩn bị là **lập chỉ mục audio tham chiếu**.
Một hash lặp nhiều lần không được tính thành nhiều phiếu trong cùng bucket.
Điểm khớp là điểm nội bộ, không phải xác suất đúng. Ngưỡng mặc định cần hiệu chỉnh trên nhạc thật.

Kho metadata/seed chỉ chứa tên bài và thông tin mô tả. Muốn nhận diện phải có fingerprint từ
đúng bản ghi âm. Một bản cover/remix có thể không khớp bản gốc. Không bảo đảm nhận diện mọi bài
ngoài kho, hát/ngân nga, thu quá nhiễu hoặc biến đổi tốc độ. Spotify phục vụ tìm kiếm/phát nhạc;
không cung cấp kho fingerprint cho thuật toán này. Không tải/trích xuất audio Spotify để lập chỉ mục.

## 1. Công cụ và cấu hình

Chạy từ terminal PowerShell ở thư mục `backend`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ffmpeg -version
ffprobe -version
```

Nếu chưa có công cụ, cài một bản FFmpeg có cả `ffmpeg.exe` và `ffprobe.exe`, sau đó
thêm thư mục `bin` vào PATH hoặc đặt đường dẫn thật trong `backend/.env.local`:

```dotenv
RECOGNITION_FFMPEG_PATH=C:/tools/ffmpeg/bin/ffmpeg.exe
RECOGNITION_FFPROBE_PATH=C:/tools/ffmpeg/bin/ffprobe.exe
RECOGNITION_MODE=landmark
RECOGNITION_LANDMARK_MIN_VOTES=12
RECOGNITION_LANDMARK_MIN_SCORE=0.05
```

Thay đường dẫn bằng nơi bạn cài công cụ. `landmark` chỉ dùng thuật toán dự án;
`hybrid` chạy thuật toán nội bộ trước, rồi AcoustID khi không tìm thấy; `acoustid` chỉ dùng dịch vụ.
AcoustID cần `ACOUSTID_CLIENT_KEY` và `CHROMAPRINT_FPCALC_PATH`. Chế độ landmark không cần chúng.

## 2. Kiểm thử cục bộ, chưa cần database

Chuẩn bị một bản ghi âm được phép sử dụng và một đoạn cắt/thu từ chính bản ghi đó:

```powershell
.\.venv\Scripts\python.exe tools/match_audio_files.py --query "C:/audio/doan-thu.wav" --reference "C:/audio/bai-goc.mp3"
```

Có thể thêm nhiều `--reference` để thử phân biệt các bài. Kết quả JSON có
`status`, `votes`, `score` và đường dẫn bản ghi phù hợp. Công cụ không ghi vào database.
Thử thêm đoạn thuộc bài ngoài kho; nếu nhận sai, tăng ngưỡng và đánh giá lại.

## 3. Thiết lập database

Source đã có bảng `music_catalog`, `music_fingerprint_points` và RPC `match_audio_landmarks`
trong `supabase/migrations/20261113_recognition_recommendations.sql`.
Nếu chưa áp dụng, đọc hướng dẫn migration trong `README_NANG_CAP_RECOGNITION_RECOMMENDATION.md`
và kiểm tra schema hiện tại trước khi chạy; không chạy lại các migration Phase 2/3 cũ một cách mù quáng.
Nếu đã dùng migration 20261107, cần bổ sung các cột mới cho catalog/preferences bằng ALTER TABLE
như hướng dẫn sửa schema đã trao đổi; CREATE TABLE IF NOT EXISTS không bổ sung cột cho bảng cũ.

Lệnh lập chỉ mục cần kết nối PostgreSQL quản trị, lấy từ mục Connect của đúng project.
Đặt `DATABASE_URL=postgresql://...` trong `backend/.env.local`; không đặt ở frontend,
không commit hoặc gửi chuỗi kết nối. Script đọc file env này kể cả khi gọi từ thư mục khác.

## 4. Nạp bản ghi âm tham chiếu

Nếu bài đã có trong `music_catalog`, lấy UUID của bài từ Supabase Table Editor:

```powershell
.\.venv\Scripts\python.exe tools/index_licensed_audio.py --track-id "UUID_CUA_BAI_HAT" --file "C:/audio/bai-goc.mp3" --i-have-rights
```

Nếu bài chưa có, tạo metadata và fingerprint cùng một lần. Điền thông tin nguồn/quyền sử dụng thật:

```powershell
.\.venv\Scripts\python.exe tools/index_licensed_audio.py --file "C:/audio/bai-goc.mp3" --title "Ten bai" --artist "Ten nghe si" --source-url "https://dia-chi-nguon-that" --source-license "Giay phep hoac quyen su dung thuc te" --i-have-rights
```

Đợi dòng `Indexed track ...` xuất hiện. Script lập chỉ mục toàn bộ bản ghi tối đa 30 phút,
thay thế fingerprint của chính UUID đó trong một transaction khi chạy lại.
Lập chỉ mục nhiều bản ghi có thể tốn dung lượng; bắt đầu bằng tập nhỏ rồi đo dung lượng/tốc độ.
Các fingerprint v2 cũ vẫn tương thích, nhưng nên lập chỉ mục lại để phủ toàn bộ bài.
Script `scripts_fingerprint_catalog.py` chỉ xuất JSON v2 để kiểm tra; không còn dùng cột `fingerprint_hashes` kiểu v1.

## 5. Chạy website

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --port 8000
```

1. Chạy frontend, đăng nhập Music Discovery rồi mở `/identify`.
2. Trang hiển thị cảnh báo nếu thiếu bộ giải mã hoặc không gọi được RPC.
3. Mở đúng bản ghi tham chiếu trên thiết bị/nguồn bạn có quyền sử dụng, đưa micro gần loa.
4. Ghi đoạn rõ 10–15 giây, bấm nhận diện.
5. Kết quả nội bộ có phương pháp MDVN Landmark và liên kết tìm bài trên Spotify.
6. Thử đoạn ở giữa/cuối bài để xác minh so khớp theo độ lệch thời gian.

`GET /api/identify/status` yêu cầu Bearer token Supabase, chỉ báo trạng thái công cụ/RPC;
RPC khả dụng **không chứng minh kho đã có fingerprint**. `503` khi kho lỗi không bị đổi thành
`not_found`. Lịch sử chỉ lưu metadata, file upload/thu âm được xóa sau xử lý tạm thời.

## 6. Đánh giá cho báo cáo

Dùng tập bản ghi có nhãn: mỗi bài lấy nhiều đoạn ở đầu/giữa/cuối, 5/10/15 giây;
thử file sạch, thu micro và các mức nhiễu. Bổ sung bài ngoài kho và khoảng im lặng.
Tách tập hiệu chỉnh ngưỡng khỏi tập báo cáo. Ghi số nhận đúng, nhận sai, không tìm thấy,
thời gian xử lý; báo cáo top-1 và false-positive trên bài ngoài kho. Không xem test tín hiệu
tổng hợp là benchmark chính xác cho nhạc thật.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Kiểm thử tự động có đoạn tổng hợp cắt lệch thời gian, giảm âm lượng, thêm nhiễu,
im lặng, chống tăng phiếu do hash lặp, và HTTP -> fingerprint -> kết quả -> lịch sử.
Test HTTP dùng RPC giả lập cùng quy tắc bỏ phiếu; chưa thay thế kiểm thử Supabase thật.
Test codec/FFmpeg tự bỏ qua khi máy chưa cài FFmpeg và FFprobe.
