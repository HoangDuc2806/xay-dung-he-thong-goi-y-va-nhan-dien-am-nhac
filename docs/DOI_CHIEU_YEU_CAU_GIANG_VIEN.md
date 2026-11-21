# Đối chiếu yêu cầu giảng viên — 19/11/2026

Người dùng xác nhận: **ít nhất 2 thuật toán gợi ý và 2 thuật toán nhận diện, có so sánh**. Ảnh ghi chú còn đề cập báo cáo, vấn đề nhạc bản quyền, tìm hiểu recommendation system và đánh giá định lượng. Một số chữ viết tay khó đọc; không diễn giải thành yêu cầu phải tải toàn bộ nhạc Spotify hay phải dùng mạng nơ-ron.

| Yêu cầu | Hiện thực và bằng chứng | Phạm vi còn giới hạn |
|---|---|---|
| Nghiên cứu recommendation system | Báo cáo phân biệt Content-based, User-based CF, Item-based CF, Hybrid và học máy | User-based CF/mạng nơ-ron mới được trình bày lý thuyết, không gắn nhãn đã cài đặt |
| Ít nhất 2 thuật toán gợi ý | TF-IDF/cosine Content-based, Item-KNN Collaborative và Hybrid 70/30. `/discover` dùng Hybrid mặc định. | Mẫu ListenBrainz 2.000 bài, độ phủ nhạc Việt còn giới hạn |
| So sánh định lượng gợi ý | Cùng split theo thời gian, cùng ứng viên, Precision/Recall/NDCG/Hit-rate@10, coverage; so thêm Popularity baseline | Offline, chưa có thử nghiệm A/B hoặc khảo sát người dùng |
| Ít nhất 2 thuật toán nhận diện | Spectral landmark + offset voting và MFCC + subsequence DTW. `/identify` có chế độ so sánh cùng một bản thu. | Kho thử nghiệm nội bộ 10 bài, tối đa 120 giây đầu mỗi bài |
| So sánh định lượng nhận diện | 176 đoạn thử cho mỗi phương pháp, với tập hiệu chỉnh riêng. Đo Top-1, recall, precision, FAR và p50/p95. | Bộ đo hiện dùng biến đổi số. Cần bản ghi thật để đo qua micro. |
| Vấn đề nguồn nhạc | Dùng 13 bản nhạc mở từ Wikimedia Commons. Mỗi bản có nguồn, tên tác giả, giấy phép và checksum. | Ghi công khi chia sẻ theo giấy phép từng bản. |
| Báo cáo | `BAO_CAO_NGHIEN_CUU_THUAT_TOAN.md`, JSON/CSV số đo và câu lệnh tái tạo | Cần điền thông tin sinh viên, mẫu trình bày của trường và bổ sung kết quả micro thực tế |

## Cách kiểm tra trên web

1. Khởi động backend/frontend như trước, đăng nhập.
2. `/discover`: bấm **Thích** một bài. Web tra thêm các nghệ sĩ ghi công trên bài rồi chấm điểm các bài tìm được cùng kho hiện có. Đối chiếu các thuật toán bằng bảng trong `backend/artifacts/evaluation.json` hoặc tham số `method` của API gợi ý.
3. `/identify`: chọn **So sánh Landmark và MFCC + DTW**. Chọn nguồn tham chiếu trên trang, phát đoạn trong thời lượng được ghi và thu WAV 5–15 giây. Chọn tên bài đã phát hoặc **Bài ngoài kho** để xem kết quả đúng sai và thời gian xử lý.
4. AudD/AcoustID vẫn là nhánh dịch vụ đang cấu hình. Chọn nhánh đó nếu cần tra kho thương mại; kết quả phải ghi nguồn dịch vụ, không trình bày là thuật toán tự cài đặt.

**Kho gợi ý và kho nhận diện khác nhau:** 2.000 dòng metadata/lượt nghe không chứa 2.000 bản audio để fingerprint. Bộ nhận diện nội bộ chỉ nhận các bản ghi đã lập chỉ mục, không tự nhận mọi bài trong catalog Spotify.

## Tái tạo kết quả

Tại `backend`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-training.txt
# Dataset ListenBrainz hiện có trong data/raw; giữ provenance URL chính thức.
.\.venv\Scripts\python.exe -m tools.prepare_recommender
# Tải nguồn CC-BY, lưu attribution; không cần token AudD.
.\.venv\Scripts\python.exe -m tools.prepare_open_audio
.\.venv\Scripts\python.exe -m tools.evaluate_recognition --hard-calibration
.\.venv\Scripts\python.exe -m pytest -q
```

Kết quả: `artifacts/evaluation.json`, `artifacts/recognition_evaluation.json`, `artifacts/recognition_evaluation.csv`. Mô hình phục vụ: `artifacts/recommender.json`, `artifacts/local_recognition.npz`. Nguồn nhạc: `artifacts/recognition_sources.json`; raw audio ở `data/recognition`, không đưa vào Git.

## Phần cần đo tiếp trước khi kết luận chất lượng thực tế

Để tổng hợp nhiều lần thu, lưu các WAV và tệp `manifest.json` cùng thư mục. Ghi trước mã bài từ `backend/artifacts/recognition_sources.json` hoặc đặt `expected` là `null` cho bài ngoài kho. Ví dụ cấu trúc:

```json
{
  "recordings": [
    {"file": "gan-loa.wav", "expected": "open-0", "condition": "gan_lo_sach"},
    {"file": "ngoai-kho.wav", "expected": null, "condition": "gan_lo_sach"}
  ]
}
```

Tại `backend`, chạy `.\.venv\Scripts\python.exe -m tools.evaluate_microphone data/recognition/microphone/manifest.json`. Kết quả lưu ở `backend/data/recognition/microphone-results.json`, dùng ngưỡng đã lưu trong bộ thử số.

- Dùng thiết bị/phòng thực: mỗi bài 3 đoạn không trùng calibration, nhiều khoảng cách, âm lượng và mức ồn; có bài ngoài kho. Ghi nhãn đúng trước khi chạy.
- Giữ nguyên ngưỡng; nếu thay đổi ngưỡng từ kết quả micro thì phải dành tập test micro khác, không dùng cùng dữ liệu vừa chỉnh vừa công bố.
- Mở rộng nhiều nghệ sĩ, thể loại và nhạc Việt có quyền sử dụng. Đo theo nhóm thể loại/thiết bị, không chỉ báo cáo một tỷ lệ tổng.
- Đánh giá nguồn metadata thiếu thể loại/ngôn ngữ; không tự gắn nhãn không có bằng chứng.
