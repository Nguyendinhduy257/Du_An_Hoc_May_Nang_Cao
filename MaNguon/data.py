r"""
Nạp dữ liệu gốc, bỏ review trùng lặp, đổi nhãn sang 0/1, chia train/val/test
rồi lưu ra CSV.

Đọc: DuLieuDeHoc\DuLieuTho\fake reviews dataset.csv
Ghi: train.csv, val.csv, test.csv trong DuLieuDeHoc\DuLieuDaXuLy\
"""

import pandas as pd
from sklearn.model_selection import train_test_split

from config import (
    LABEL_COLUMN,
    LABEL_MAP,
    PROCESSED_DIR,
    RANDOM_SEED,
    RAW_CSV_PATH,
    TEST_CSV_PATH,
    TEST_RATIO,
    TEXT_COLUMN,
    TRAIN_CSV_PATH,
    TRAIN_RATIO,
    VAL_CSV_PATH,
    VAL_RATIO,
)
from file_safety import save_text_with_warning


def load_reviews(csv_path):
    """Đọc CSV gốc và bỏ các review trùng nguyên văn."""
    reviews = pd.read_csv(csv_path, encoding="utf-8")

    # Bỏ trùng vì 20 review xuất hiện 2 lần. Nếu giữ nguyên, cùng một câu có
    # thể rơi vào cả train lẫn test, model chỉ cần "nhớ" câu đó là đúng, điểm
    # test bị thổi phồng (data leakage) và không phản ánh năng lực thật.
    reviews = reviews.drop_duplicates(subset=TEXT_COLUMN, keep="first")
    reviews = reviews.reset_index(drop=True)
    return reviews


def add_binary_label(reviews):
    """Thêm cột label_binary: OR -> 0, CG -> 1."""
    reviews = reviews.copy()

    # Tạo cột mới thay vì ghi đè để giữ cột label gốc, còn đối chiếu khi kiểm
    # tra dữ liệu hoặc debug.
    reviews["label_binary"] = reviews[LABEL_COLUMN].map(LABEL_MAP)

    # Kiểm tra NaN vì map() trả NaN cho nhãn lạ. Báo lỗi ngay còn hơn để NaN
    # âm thầm trôi vào model.
    unknown_labels = reviews.loc[reviews["label_binary"].isna(), LABEL_COLUMN].unique()
    if len(unknown_labels) > 0:
        raise ValueError(f"Có nhãn không nằm trong LABEL_MAP: {unknown_labels}")

    reviews["label_binary"] = reviews["label_binary"].astype(int)
    return reviews


def split_reviews(reviews):
    """Chia phân tầng theo tỉ lệ trong config (mặc định 70/15/15)."""
    # Chia 2 lần vì train_test_split chỉ tách được thành 2 phần. Lần 1 tách
    # train ra khỏi phần còn lại (val + test).
    train_reviews, temp_reviews = train_test_split(
        reviews,
        test_size=(1.0 - TRAIN_RATIO),
        random_state=RANDOM_SEED,
        stratify=reviews["label_binary"],
    )

    # stratify giữ tỉ lệ CG/OR giống nhau ở cả 3 tập, tránh việc tập test vô
    # tình lệch lớp so với train.
    # test_share là tỉ lệ test trong phần tạm (val + test).
    test_share = TEST_RATIO / (VAL_RATIO + TEST_RATIO)
    val_reviews, test_reviews = train_test_split(
        temp_reviews,
        test_size=test_share,
        random_state=RANDOM_SEED,
        stratify=temp_reviews["label_binary"],
    )
    return train_reviews, val_reviews, test_reviews


def save_splits(train_reviews, val_reviews, test_reviews):
    """Lưu 3 tập ra CSV, cảnh báo nếu nội dung ghi đè khác bản cũ."""
    # to_csv(None) trả về chuỗi trong bộ nhớ, để file_safety so sánh với bản
    # cũ trước khi quyết định ghi.
    save_text_with_warning(TRAIN_CSV_PATH, train_reviews.to_csv(index=False))
    save_text_with_warning(VAL_CSV_PATH, val_reviews.to_csv(index=False))
    save_text_with_warning(TEST_CSV_PATH, test_reviews.to_csv(index=False))


def print_summary(train_reviews, val_reviews, test_reviews):
    print("=== CHIA DỮ LIỆU ===")
    for name, split in (
        ("train", train_reviews),
        ("val", val_reviews),
        ("test", test_reviews),
    ):
        counts = split["label_binary"].value_counts().sort_index()
        print(
            f"{name:>5}: {len(split):>6} dòng | "
            f"thật(0)={counts.get(0, 0):>6} | giả(1)={counts.get(1, 0):>6}"
        )


def main():
    reviews = load_reviews(RAW_CSV_PATH)
    reviews = add_binary_label(reviews)
    train_reviews, val_reviews, test_reviews = split_reviews(reviews)
    save_splits(train_reviews, val_reviews, test_reviews)
    print_summary(train_reviews, val_reviews, test_reviews)
    print(f"\nThư mục dữ liệu: {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
