# Dữ liệu đồ án — Fake Review Detection

## Nguồn

| Mục | Giá trị |
|---|---|
| Dataset | **Fake Reviews Dataset** (Salminen et al., 2022) |
| Kaggle | `mexwell/fake-reviews-dataset` |
| URL | https://www.kaggle.com/datasets/mexwell/fake-reviews-dataset |
| License | **CC BY 4.0** |
| Tải ngày | 2026-11-09 |
| SHA256 (zip) | `5d55e1383ecf7f19fe6497a11f14116c2a72bbbbcd949727fedb533a03c635e7` |

**Citation:**
> Salminen, J., Kandpal, C., Kamel, A. M., Jung, S., & Jansen, B. J. (2022).
> Creating and detecting fake reviews of online products.
> *Journal of Retailing and Consumer Services, 64*, 102771.
> https://doi.org/10.1016/j.jretconser.2021.102771

## Cấu trúc thư mục

```
DuLieuDeHoc/
├── DuLieuTho/
│   ├── fake reviews dataset.csv     # dữ liệu gốc, KHÔNG sửa
│   ├── fake-reviews-dataset.zip     # file tải gốc (provenance)
│   └── SOURCE.json                  # metadata + audit
├── DuLieuDaXuLy/
│   ├── train.csv                    # 70% sau chia stratified, seed 42
│   ├── val.csv                      # 15% dùng chọn ngưỡng + hiệu chuẩn
│   └── test.csv                     # 15% chỉ dùng một lần để báo cáo
└── README.md
```

`DuLieuTho/` chỉ đọc: mọi thao tác làm sạch ghi sang `DuLieuDaXuLy/`, không sửa
file gốc để còn đối chiếu và tính lại được.

## Mô tả cột

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `category` | str | 10 nhóm sản phẩm Amazon (Kindle, Books, Pet, Home & Kitchen, Electronics, Sports, Tools, Clothing, Toys, Movies) |
| `rating` | float | Số sao 1–5 |
| `label` | str | `OR` = review thật (người viết), `CG` = review giả (máy sinh) |
| `text_` | str | Nội dung review |

## Kết quả audit

| Chỉ số | Giá trị |
|---|---|
| Số dòng | **40,432** |
| Số cột | 4 |
| CG (fake) | **20,216** |
| OR (real) | **20,216** |
| Cân bằng lớp | **Có** (50:50 chính xác) |
| Giá trị thiếu | 0 |
| Text rỗng | 0 |
| Trùng toàn dòng | 12 |
| Trùng text | 20 |
| Số category | 10 |
| Độ dài text (ký tự) | min 24 · median 198 · mean 351.27 · p95 1209 · max 2827 |

## Lưu ý quan trọng cho báo cáo

1. **Số dòng thực tế là 40.432**, không phải đúng 40.000 như mô tả Kaggle (làm tròn). Phải ghi đúng con số.
2. Nhãn gốc chỉ có **2 lớp CG/OR**. Việc tách Fake thành Bot vs Boost-rating là **rule layer tự định nghĩa**, không có nhãn gốc — phải ghi rõ trong báo cáo.
3. Đây là dữ liệu **tiếng Anh**, domain Amazon. Không suy rộng sang tiếng Việt.
4. `category` đều có hậu tố `_5` (5-core filtering của Amazon).
5. Có 20 text trùng lặp — cần xử lý khi chia train/test để tránh **leakage** (cùng một text xuất hiện ở cả train và test).
