r"""
Chuyển văn bản review thành ma trận số bằng TF-IDF.

Nhận ba DataFrame train/val/test (cột text_), trả X_train, X_val, X_test dạng
ma trận thưa và vectorizer đã fit.
"""

from sklearn.feature_extraction.text import TfidfVectorizer

from config import TFIDF_PARAMS, TEXT_COLUMN


def fit_transform_features(train_reviews, val_reviews, test_reviews):
    """Fit TF-IDF trên train, chỉ transform trên val/test."""
    vectorizer = TfidfVectorizer(**TFIDF_PARAMS)

    # Chỉ fit trên train vì fit sẽ xây bộ từ vựng và trọng số IDF từ dữ liệu.
    # Nếu fit trên val/test, thông tin của tập đánh giá bị "nhìn thấy" trước,
    # thành data leakage: kết quả đẹp nhưng không dùng được ngoài thực tế.
    X_train = vectorizer.fit_transform(train_reviews[TEXT_COLUMN])
    X_val = vectorizer.transform(val_reviews[TEXT_COLUMN])
    X_test = vectorizer.transform(test_reviews[TEXT_COLUMN])

    return X_train, X_val, X_test, vectorizer
