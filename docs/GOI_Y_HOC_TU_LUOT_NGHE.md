# Gợi ý học từ lượt nghe — bản triển khai 14/11/2026

**Cập nhật giao diện 20/11:** đã bỏ khối nhập tài khoản ListenBrainz. Trang Khám phá dùng sở thích và phản hồi Thích/Bỏ qua trong web; chọn Collaborative, Content-based hoặc Hybrid ngay cạnh danh sách gợi ý. Không cần tài khoản dịch vụ khác. ListenBrainz vẫn là nguồn dataset huấn luyện; API đọc hồ sơ công khai được giữ cho nghiên cứu, nhưng không được gọi từ trang này. Phần hướng dẫn nhập tên ListenBrainz ở bản 14/11 bên dưới là lịch sử.

**Cập nhật 19/11:** đã có thêm Content-based và Hybrid, cùng phép đo so sánh. Xem [báo cáo nghiên cứu hiện hành](BAO_CAO_NGHIEN_CUU_THUAT_TOAN.md); các kết quả ở dưới giữ lại cho bản Item-KNN đầu tiên.

## Cách thử ngay

1. Chạy backend và frontend như trước, đăng nhập rồi mở `/discover`.
2. Nếu đang chọn thể loại/tâm trạng/ngôn ngữ, bấm **Bỏ bộ lọc để khám phá theo gu đã học**. Nhiều bài trong dataset chưa có các nhãn này; không tự suy đoán nhãn để lấp dữ liệu.
3. Khi chưa có hồ sơ, danh sách là các bài phổ biến trong mẫu ListenBrainz. Bấm Thích vài bài; lần tải tiếp theo dùng item-KNN tìm các bài thường được những người có gu gần bạn nghe cùng. Bài làm cơ sở không xuất hiện lại trong danh sách đề xuất.
4. Nếu có tài khoản ListenBrainz với dữ liệu nghe, nhập tên tài khoản và bấm **Dùng lịch sử nghe**. Backend đọc một trang tối đa 200 lượt nghe công khai, đối chiếu với tập bài đã học. Không cần API token; không xác minh quyền sở hữu tài khoản hay gọi đây là kết nối OAuth.
5. Dùng **Tải lại gợi ý** để đọc lại hồ sơ; API có cache 3 phút. **Ngừng dùng lịch sử** quay lại phản hồi trong web. Tải lại trang cũng bỏ tên đã nhập. Tên không được lưu vào hồ sơ Supabase.
6. **Tìm Spotify** tìm bài để phát bằng tích hợp hiện có. Không dùng sự kiện SDK, bảng lịch sử Spotify, độ phổ biến hay audio features Spotify để huấn luyện/xếp hạng.

Thích/Bỏ qua cập nhật hồ sơ cá nhân ngay, không huấn luyện lại toàn bộ mô hình sau mỗi lần bấm. Mẫu hiện tại thiên về nhạc quốc tế; không đảm bảo có B-Ray hoặc mọi bài Việt. Lịch sử không khớp mẫu sẽ được báo rõ, không tạo dữ liệu giả.

## Dữ liệu và thuật toán

- Nguồn: [ListenBrainz official incremental dump](https://data.metabrainz.org/pub/musicbrainz/listenbrainz/incremental/listenbrainz-dump-2782-20261113-000002-incremental/), giấy phép [CC0 của ListenBrainz](https://metabrainz.org/datasets/postgres-dumps).
- Kiểm tra SHA256 chính thức: `bed3ff393f805afa211771ab433b746f923c95ad17e7d52bd7f77fc7d0491961`.
- Đọc JSON-lines trực tiếp trong tar.zst, không giải nén đường dẫn từ archive ra hệ thống. Bỏ bản ghi trước 13/10/2026 và bản ghi xác định có nguồn Spotify; không nhập service IDs, tags cộng đồng, âm thanh, tên người dùng vào artifact.
- Từ 6.177.546 dòng thô, chọn 2.000 bài có ít nhất 3 người nghe trong phần train, người nghe có ít nhất 5 bài. Mẫu cuối: **167.468 lượt nghe, 3.283 người nghe, 2.000 bài**. ID người nghe được băm trong RAM; artifact triển khai chỉ chứa metadata bài, số người nghe tổng hợp và hàng xóm.
- Thuật toán: **Item-based Collaborative Filtering / Item-KNN**. Ma trận người–bài dùng `log(1 + play_count)`, cosine similarity giữa các cột bài hát, giảm trọng số bằng `shared_users / (shared_users + 10)`, cần ít nhất 2 người cùng nghe, giữ tối đa 50 hàng xóm/bài.
- Hồ sơ cá nhân: trọng số lượt nghe ListenBrainz và phản hồi Thích/Lưu; lựa chọn nghệ sĩ chỉ là cơ sở khởi đầu, không giả lập lượt nghe. Không thích/Bỏ qua và nghệ sĩ bị chặn bị loại trước khi trả kết quả. Giữ các bộ lọc đã chọn.
- Khi chưa có hồ sơ: số người nghe độc lập trong tập train là baseline độ phổ biến. Khi mẫu không hỗ trợ lựa chọn hiện tại: chuyển về metadata, báo phương pháp thực tế qua `model.algorithm`.
- Code: `backend/app/services/collaborative.py`, `backend/tools/train_recommender.py`, `backend/app/services/listenbrainz_profile.py`. API điều phối ở `backend/app/routers/recommendations.py`.

## Đánh giá thực tế

Chia theo một mốc thời gian toàn cục **12/11/2026 17:30:40 UTC**: train 144.628, test 22.840 lượt. Chọn vocabulary và người nghe từ phần train, không chọn theo độ phổ biến tương lai. Đánh giá các bài mới với từng người, loại bài đã có trong train, xét toàn bộ ứng viên trong vocabulary thay vì lấy vài negative ngẫu nhiên. Có **1.154 người** đủ điều kiện đánh giá.

| Chỉ số | Item-KNN | Độ phổ biến |
|---|---:|---:|
| Precision@10 | 0,054506 | 0,011438 |
| Recall@10 | 0,139730 | 0,016371 |
| NDCG@10 | 0,114844 | 0,019857 |
| Hit rate@10 | 0,272097 | 0,045927 |
| Catalog coverage | 0,655500 | 0,019500 |

Đây là kết quả trên mẫu đã lọc 2.000 bài, **không phải độ chính xác trên toàn bộ Spotify hay trên nhạc Việt**. Vocabulary coverage 1,0 là do tập đo đã giới hạn trong vocabulary; không dùng số đó để khẳng định phủ toàn bộ nhạc. Sau khi đo, refit graph phục vụ trên toàn bộ mẫu đã chọn. Báo cáo máy đọc: `backend/artifacts/evaluation.json`; artifact: `backend/artifacts/recommender.json`.

## Tái tạo và bổ sung kho tự động

Chạy PowerShell tại thư mục `backend`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-training.txt
.\.venv\Scripts\python.exe -m tools.prepare_recommender
.\.venv\Scripts\python.exe -m tools.export_recommender_catalog
# DATABASE_URL phải nằm trong môi trường terminal quản trị, không gửi lên frontend/chat.
.\.venv\Scripts\python.exe -m tools.import_catalog_csv data/catalog_listenbrainz.csv --acknowledge-provenance
```

Lệnh đầu tải khoảng 316 MiB nếu chưa có archive, đối chiếu checksum rồi train/evaluate. Không cần tự nhập từng bài. Có thể đổi `--url`, `--since`, `--max-items` và `--max-users` để mở rộng mẫu; giới hạn mặc định tránh tải cả kho khổng lồ. Raw dataset và CSV được gitignore. Không chạy lại import metadata thủ công nếu artifact đã có trong Supabase hiện tại.

Đã nhập 2.000 dòng metadata học được vào Supabase hiện tại bằng ID ổn định, giữ các dòng cũ. Script CSV cũng giữ ID tương ứng để phản hồi FK và graph khớp nhau. API đọc catalog theo trang 1.000 dòng, tối đa 5.000. Không thay RLS hoặc quyền truy cập bảng.

## Phân biệt với nhận diện

Recommender này không nhận diện âm thanh. AudD là dịch vụ đối chiếu đoạn thu với kho của họ; kết quả không khớp không chứng minh bài không có trong kho. Thuật toán landmark trong source là nhánh đối chiếu kho riêng, cần fingerprint các bản ghi tham chiếu có quyền sử dụng; nó không dùng dataset lượt nghe ở trên.

Tài liệu API: [lượt nghe gần đây](https://listenbrainz.readthedocs.io/en/latest/users/api/core.html), [định dạng dump](https://listenbrainz.readthedocs.io/en/latest/users/listenbrainz-dumps.html), [Spotify policy](https://developer.spotify.com/policy).
