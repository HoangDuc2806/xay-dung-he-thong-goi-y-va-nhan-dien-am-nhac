# Demo: mở nhạc trên điện thoại và nhận diện qua micro máy tính

## Cách chạy nhanh

1. Đăng ký/đăng nhập tại https://dashboard.audd.io/ và lấy API token.
   Kiểm tra hạn mức/gói sử dụng trên dashboard; chi phí do dịch vụ quy định.
2. Mở `backend/.env.local`, thêm hoặc cập nhật **một dòng duy nhất cho mỗi biến**:

   ```dotenv
   RECOGNITION_MODE=audd
   AUDD_API_TOKEN=TOKEN_THAT_CUA_BAN
   ```

   Không đưa token vào frontend, không gửi token qua chat. Những cấu hình Supabase/Spotify hiện có vẫn được sử dụng.
3. Khởi động lại backend để nạp cấu hình (chạy trong thư mục backend):

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --port 8000
   ```

4. Chạy frontend bằng `npm run dev` trong thư mục frontend. Đăng nhập rồi mở
   http://127.0.0.1:3000/identify và tải lại trang.
5. Phần trạng thái phải hiển thị đang chọn AudD, không báo thiếu token.
   Trạng thái chỉ xác nhận token đã được cấu hình; yêu cầu nhận diện thực mới xác minh được token/hạn mức.
6. Mở Spotify trên điện thoại, phát qua **loa ngoài**. Để gần micro máy tính,
   chọn đoạn có giọng hát hoặc giai điệu rõ, tránh khoảng im lặng và lời nói lấn át nhạc.
7. Bấm Bắt đầu ghi âm, cấp quyền micro. Đợi 10–15 giây hoặc bấm Dừng.
8. Nghe lại bản ghi ngay trên trang: phải nghe rõ nhạc. Bấm Nhận diện bài hát.
9. Nếu tìm thấy, trang hiện tên bài, nghệ sĩ và nguồn **AudD (dịch vụ nhận diện)**.
   Có liên kết trực tiếp Spotify nếu dịch vụ trả về; luôn có nút tìm trên Spotify.

## Có cần tự nạp kho nhạc không?

Chế độ `audd` tra kho của AudD, không cần tự nạp music_catalog/fingerprint, không cần
DATABASE_URL quản trị. Token đăng nhập Supabase vẫn cần cho API và lưu lịch sử.
Thiếu bảng lịch sử không chặn kết quả nhận diện; backend ghi cảnh báo trong log.

Trình duyệt chuyển bản thu sang PCM WAV mono 16000 Hz, backend xác thực cấu trúc WAV và
gửi tối đa 12 giây đầu. Luồng WAV này không cần FFmpeg/FFprobe. Upload MP3/WebM/M4A
trực tiếp vẫn cần FFmpeg/FFprobe. Nếu trình duyệt không chuyển được WAV, trang giữ
bản ghi gốc và thông báo cách xử lý; hãy dùng Chrome/Edge mới hoặc cài bộ giải mã backend.

Đoạn audio chỉ được gửi tới AudD khi bấm Nhận diện. Website chỉ giữ file tạm và metadata
kết quả; việc xử lý tại dịch vụ phụ thuộc điều khoản của AudD.

## Chuẩn bị trước khi gặp thầy

- Thử ít nhất vài bài bạn định demo, ghi lại số nhận đúng/không tìm thấy và thời gian xử lý.
- Thử cả bài Việt và quốc tế bạn muốn hỗ trợ, nhiều đoạn khác nhau của cùng bài.
- Không cam kết nhận được mọi bài: phụ thuộc kho dịch vụ, bản remix/cover, nhiễu, micro và Internet.
- Không dùng kết quả Now Playing làm bằng chứng nhận diện âm thanh: đó là API đọc metadata riêng.
- Ghi rõ với thầy: demo mở rộng kho dùng AudD. Thuật toán tự xây là `mdvn-landmark-v2`
  (STFT/FFT, đỉnh phổ, hash, temporal-offset voting), thử riêng bằng `RECOGNITION_MODE=landmark`
  và kho tham chiếu đã lập chỉ mục. Không mô tả kết quả AudD là thuật toán do mình viết.

## Xử lý lỗi nhanh

- Thiếu `AUDD_API_TOKEN`: kiểm tra đúng backend/.env.local, tránh biến trùng, restart backend.
- Token sai/hết hạn mức: xem AudD dashboard, sửa token rồi restart.
- Không nghe thấy nhạc khi nghe lại: kiểm tra micro đầu vào, quyền micro, âm lượng loa điện thoại.
- Dịch vụ không kết nối: kiểm tra Internet, thử lại một lần; không tự gửi lặp liên tục.
- Không tìm thấy: thử đoạn khác có giai điệu rõ hơn hoặc một bài khác; không giả lập kết quả thành công.

Tài liệu API đối chiếu: https://docs.audd.io/.md

Kiểm thử tự động cho provider sử dụng HTTP giả lập, không tiêu tốn hạn mức.
Kết quả tích hợp thực tế chỉ được xác nhận sau khi cấu hình token và thử bản ghi thật.
