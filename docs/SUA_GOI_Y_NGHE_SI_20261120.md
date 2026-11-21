# Sửa gợi ý nghệ sĩ và giao diện — 20/11/2026

## Vấn đề được sửa

Ảnh lỗi chọn B-Ray nhưng không có kết quả có nhiều nguyên nhân: kho cũ chỉ có 8 dòng gắn ngôn ngữ Việt và không có B-Ray; so tên nghệ sĩ hợp tác như một chuỗi duy nhất; coi các bài chọn làm mẫu từ nghệ sĩ yêu thích là đã nghe rồi loại chúng; mô hình cũ không dùng được metadata của bài bổ sung sau huấn luyện.

Đã sửa:

- Ẩn chọn thuật toán và điểm nội bộ trên trang Khám phá. Web tự dùng Hybrid; các phương pháp vẫn có trong API và script để nghiên cứu, không yêu cầu người nghe lựa chọn.
- Tách rõ bài làm mẫu theo nghệ sĩ với bài thực sự đã Thích/nghe. Bài của nghệ sĩ yêu thích vẫn được đề xuất; dành đủ chỗ cho nghệ sĩ đó thay vì giới hạn mặc định hai bài.
- Nhận B-Ray/B Ray/bray qua chuẩn hóa, nhận thành viên trong credit như `B-Ray & AMEE`; không dùng fuzzy substring. Nghệ sĩ bị chặn và bài Không thích/Bỏ qua tiếp tục bị loại, kể cả dòng trùng từ nguồn khác.
- Cập nhật graph Content-based bằng metadata độc lập đang có, cache theo dữ liệu và chạy ngoài event loop. Bài mới chưa có lượt nghe sử dụng nội dung; không tạo play count hoặc gán giả bằng chứng collaborative.
- Khi có nghệ sĩ/bài đã thích làm cơ sở mạnh, nhãn còn thiếu không bị coi là nhãn mâu thuẫn. Nhãn có sẵn nhưng trái với lựa chọn vẫn bị loại. Không tự gắn mood, genre hay ngôn ngữ không có bằng chứng.
- Bổ sung kiểm thử bài mới, bài hợp tác, seed nghệ sĩ, nhãn thiếu/mâu thuẫn, phản hồi âm và trùng bản ghi.

## Dữ liệu bổ sung và kiểm chứng

MusicBrainz core metadata CC0, 6 nghệ sĩ truy vấn được: B-Ray, HIEUTHUHAI, Rhymastic, JustaTee, Phương Ly, Chillies. Không dùng Spotify content để xếp hạng/huấn luyện, không tải audio, không nhập user tags cộng đồng. Bỏ một bản cover country bị gán nhầm cùng artist MBID với B-Ray và các track tên Intro/Outro/Skit. AMEE/Đen có danh tính tìm kiếm mơ hồ nên không tự chọn bừa; AMEE vẫn xuất hiện trong credit hợp tác xác minh được.

- Artifact có **142** bản ghi hợp lệ: `backend/artifacts/catalog_enrichment.json` kèm nguồn từng bản ghi và hash cache.
- Nhập thực tế **136 dòng mới**, bỏ 6 bản đã có cùng tên/nghệ sĩ. Supabase có **2.159 bài active**, gồm **16 bài có B-Ray trong credit**.
- Vai trò authenticated đọc được đủ 16 bài dưới RLS hiện có. Không đổi schema hoặc RLS.
- Kiểm tra inference với catalog mở rộng trả 16 gợi ý cho `b-ray`, kể cả khi chọn vi/sad nhưng các bài này chưa có nhãn. Trường mood/ngôn ngữ không bị giả lập.
- HTTP route dùng 16 bản ghi B-Ray lấy từ Supabase, các bài mô hình hiện có và fixture xác thực trả 200, gồm Do for Love, Chờ Anh Về, Ex's Hate Me. Đây không phải kiểm thử đăng nhập bằng trình duyệt thật.

Source tham khảo: [MusicBrainz data license](https://musicbrainz.org/doc/About/Data_License), [API search](https://musicbrainz.org/doc/MusicBrainz_API/Search). Không thể đảm bảo mọi nghệ sĩ đều có dữ liệu; nếu nguồn độc lập không có nghệ sĩ thì vẫn phải thông báo thiếu, không lấy nhạc ngẫu nhiên và gọi đó là phù hợp.

## Tái tạo bổ sung

Chạy tại `backend`:

```powershell
.\.venv\Scripts\python.exe -m tools.fetch_musicbrainz_catalog
.\.venv\Scripts\python.exe -m tools.build_musicbrainz_enrichment --sql-output ../supabase/seeds/20261120_musicbrainz_discovery.sql
```

Fetcher tuân thủ <=1 request/giây, cache, retry có giới hạn và không chọn danh tính mơ hồ. MusicBrainz có thể báo 503; khi không lấy được nguồn thì không tự tạo dữ liệu. Seed đã tạo có thể chạy lại trong SQL Editor quản trị; không cần chạy lại cho database hiện tại đã nhập.

## Giới hạn số đo

Số liệu offline trong báo cáo 19/11 mô tả mẫu ListenBrainz 2.000 bài và giao thức lúc đó. Thay đổi lần này xác minh tính liên quan của các trường hợp cụ thể và hành vi hệ thống; **chưa có benchmark mới để khẳng định precision/recall tổng thể tăng**. Cần tập test và phản hồi người dùng đa dạng hơn để đánh giá chất lượng thực tế.
