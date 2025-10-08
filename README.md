# HEIC → PNG Converter (GUI) – README

## 👨‍💻 Tác giả
- **Nguyễn Gia Bảo** – MSSV **21151073**  
- **Nguyễn Xuân Hoàng** – MSSV **21151459**  
Sinh viên **Trường Đại học Sư Phạm Kĩ Thuật TP.HCM**

---

## 🎯 Mục tiêu & Chức năng chính
Công cụ **chuyển đổi ảnh HEIC/HEIF sang PNG** với **giao diện Tkinter**, tối ưu cho xử lý nhiều ảnh:

- **Chuyển HEIC/HEIF → PNG** (PNG là **lossless**, không giảm chất lượng).
- **Giữ siêu dữ liệu** (nếu có): **EXIF**, **ICC profile**.
- **Đa luồng (multi-thread)**: tăng tốc khi chuyển **hàng trăm ảnh**.
- **Giữ nguyên thư mục gốc**; tạo output mới theo mẫu **`ConvertToPNGOutput*index`** trong thư mục đích.
- **Quét đệ quy** (recursive) thư mục con.
- **Bốn chế độ scale ảnh**:
  1) **Giữ nguyên**  
  2) **Fit within (giữ tỉ lệ)** – co ảnh *lọt vào* khung W×H, không méo  
  3) **Exact (kéo dãn)** – ép đúng W×H (có thể méo)  
  4) **Pad to size (không méo)** – co ảnh giữ tỉ lệ rồi **thêm viền** (chọn **màu nền**) để ra đúng W×H  
- Tùy chọn **Không upscale** (không phóng lớn ảnh nhỏ hơn mục tiêu).
- **Compress level 0–9** cho PNG (chỉ ảnh hưởng dung lượng/tốc độ, **không ảnh hưởng chất lượng**).
- **Thanh tiến trình mượt** (~60 FPS) với nội suy (easing), tự chuyển **indeterminate → determinate**.
- **Nút Stop**: dừng **an toàn (graceful)** – ngừng xếp việc mới, hủy việc chưa chạy, đợi các ảnh đang xử lý dở hoàn tất.
- **Nút Browse…** chọn nhanh thư mục vào/ra.
- **Bỏ qua các file đã tồn tại** ở đích (không tạo trùng).

---

## 📦 Yêu cầu hệ thống
- **Python** 3.10+ (khuyến nghị 3.11–3.13)
- **Windows 10/11** (chạy tốt nhất; vẫn có thể chạy trên macOS/Linux nếu cài đúng thư viện)
- Thư viện:
  ```bash
  pip install pillow pillow-heif
  ```

> `pillow-heif` đi kèm libheif qua wheel trên Windows — thường không cần cài thêm codec.

---

## 📁 Cấu trúc đề xuất
```
HEIC_To_PNG_Tool/
├─ heic_to_png_gui.py      # file chính (GUI)
└─ README.md               # tài liệu này
```

---

## 🚀 Cài đặt & Chạy
1. Tạo môi trường (khuyến nghị):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. Cài thư viện:
   ```bash
   pip install pillow pillow-heif
   ```
3. Chạy công cụ:
   ```bash
   python heic_to_png_gui.py
   ```

---

## 🖱️ Hướng dẫn sử dụng (GUI)

### 1) Khai báo đường dẫn
- **INPUT_ROOT**: thư mục chứa ảnh **HEIC/HEIF**.  
  *VD*: `C:\Users\NguyenBao\Pictures\Data_Final_Prj`
- **OUTPUT_BASE**: thư mục sẽ tạo thư mục output theo mẫu `ConvertToPNGOutput*index`.  
  *VD*: `C:\Users\NguyenBao\Pictures`
- **OUTPUT_PREFIX**: tiền tố thư mục xuất.  
  *VD*: `ConvertToPNGOutput` → tạo `ConvertToPNGOutput1`, `ConvertToPNGOutput2`, …

> Có thể bấm **Browse…** để chọn nhanh.

### 2) Tuỳ chọn chung
- **Recursive**: quét cả thư mục con.
- **Compress level (0–9)**:  
  - `0`: nhanh, file lớn hơn một chút  
  - `9`: chậm hơn, file nhỏ hơn.  
  *(PNG luôn lossless – ảnh không bị giảm chất lượng.)*

### 3) Scale ảnh (tùy chọn)
Chọn **một** chế độ:
- **Giữ nguyên**: không scale.
- **Fit within (giữ tỉ lệ)**: nhập `Width` và/hoặc `Height` (được phép thiếu 1 cạnh) → ảnh co để lọt khung, **không méo**, **không pad**.
- **Exact (kéo dãn)**: nhập **cả** `Width` và `Height` → ảnh bị kéo dãn để đúng kích thước (có thể méo).
- **Pad to size (không méo)**: nhập **cả** `Width` và `Height`, chọn **màu nền** → ảnh co vừa khung, **thêm viền** để đúng kích thước, **không méo**.  
- Tuỳ chọn **Không upscale**: nếu bật, ảnh nhỏ hơn mục tiêu sẽ **không** bị phóng lớn (tránh giảm cảm nhận chất lượng), chỉ pad thêm (với chế độ Pad) hoặc giữ kích thước nhỏ (với Fit).

### 4) Thực thi
- Bấm **Convert** để bắt đầu.
- **Progress bar** hiển thị mượt; trạng thái sẽ cập nhật số file đã xử lý.
- Bấm **Stop** để dừng **an toàn**: tác vụ mới không được xếp; việc đang chạy sẽ hoàn tất rồi dừng.

---

## 💡 Ghi chú kỹ thuật
- **Giữ EXIF & ICC** (nếu có) sang PNG → màu sắc/siêu dữ liệu được bảo toàn tối đa.
- **Bỏ qua file đã tồn tại** ở đích để tiết kiệm thời gian xử lý lần sau.
- **Đa luồng**: dùng `ThreadPoolExecutor` với số luồng phù hợp CPU (tối đa 32).
- **DPI/HiDPI**: chương trình bật **DPI awareness** trên Windows để giao diện sắc nét.

---

## 🧰 Troubleshooting
- **Lỗi mở HEIC**: cập nhật thư viện
  ```bash
  pip install --upgrade pillow pillow-heif
  ```
- **Ảnh ra không đúng màu**: kiểm tra **ICC profile** nguồn; PNG có thể nhúng ICC, nhưng một số trình xem ảnh bỏ qua profile.
- **Thiếu quyền ghi**: đảm bảo có quyền ghi vào **OUTPUT_BASE**.
- **Stop** không dừng ngay lập tức: Stop là **graceful** – đợi các ảnh **đang xử lý dở** xong rồi mới kết thúc.

---

## 🛠️ Đóng gói .EXE (tuỳ chọn – Windows)
Dùng **PyInstaller**:
```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name "HEIC_To_PNG_Tool" heic_to_png_gui.py
```
File EXE nằm trong `dist/`.

---

## 📜 Giấy phép
Dự án phục vụ mục đích học tập/nghiên cứu tại **ĐH Sư Phạm Kĩ Thuật TP.HCM**.  
Có thể sử dụng nội bộ; nếu phát hành rộng rãi, vui lòng ghi công **tác giả**.

---

## 📧 Liên hệ
- **Nguyễn Gia Bảo** – MSSV **21151073**  
- **Nguyễn Xuân Hoàng** – MSSV **21151459**  
Trường **ĐH Sư Phạm Kĩ Thuật TP.HCM**

--- 

Chúc bạn chuyển ảnh thật nhanh và đẹp! ✨
