r"""
PCA và LDA cài bằng numpy thuần, đối chứng scikit-learn.

Nội dung thuộc Học máy nâng cao 004295, Chương 4 mục 4.4-4.5 (giảm chiều).
PCA không dùng nhãn, giữ hướng có phương sai lớn nhất. LDA dùng nhãn, giữ
hướng phân tách lớp tốt nhất theo tỉ lệ scatter giữa lớp / trong lớp.

Dữ liệu minh hoạ cố ý có một chiều nhiễu phương sai rất lớn không mang nhãn:
PCA chọn chiều đó trước, LDA bỏ qua nó. Vì vậy so sánh độ đúng sau khi chiếu
là thấy rõ khác biệt giữa hai cách giảm chiều.

Chạy: python MaNGuon\pca_lda_tu_cai.py
Mã thoát 0 nếu PCA và LDA tự cài khớp sklearn. File này không tham gia
run_all.py vì là bài minh hoạ, không làm đổi fingerprint/cache của pipeline.

Viết tắt:
    PCA - principal component analysis (phân tích thành phần chính)
    LDA - linear discriminant analysis (phân tích tuyến tính Fisher)
    S_W - scatter trong lớp (within-class scatter)
    S_B - scatter giữa lớp (between-class scatter)
"""

import atexit

import numpy as np
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

from don_rac import auto_cleanup
from config import FROM_SCRATCH_SAMPLE_COUNT, FROM_SCRATCH_SEED

atexit.register(auto_cleanup)


def make_demo_data(sample_count, seed):
    """
    Sinh ba lớp, bốn chiều: chiều 0 là nhiễu lớn, chiều 3 là nhiễu vừa,
    chiều 1 và 2 mang tín hiệu lớp nhưng phương sai nhỏ hơn nhiễu.

    PCA xếp theo phương sai nên sẽ ưu tiên nhiễu; LDA xếp theo khả năng tách
    lớp nên sẽ ưu tiên tín hiệu. Đây là điểm khác biệt cần minh hoạ.
    """
    rng = np.random.default_rng(seed)
    per_class = sample_count // 3
    class_means = np.array([[-3.0, -2.0], [0.0, 2.5], [3.0, -1.5]])

    features = np.zeros((3 * per_class, 4))
    target = np.repeat(np.arange(3), per_class)

    for class_index in range(3):
        rows = slice(class_index * per_class, (class_index + 1) * per_class)
        features[rows, 0] = rng.normal(0.0, 4.0, per_class)
        features[rows, 1] = rng.normal(class_means[class_index, 0], 0.6, per_class)
        features[rows, 2] = rng.normal(class_means[class_index, 1], 0.6, per_class)
        features[rows, 3] = rng.normal(0.0, 1.5, per_class)

    order = rng.permutation(features.shape[0])
    return features[order], target[order]


def pca_fit(features):
    """
    PCA bằng phân rã trị riêng của ma trận hiệp phương sai.

    Chia cho n - 1 giống sklearn (ước lượng không chệch). np.linalg.eigh
    dùng cho ma trận đối xứng nên ổn định và trả trị riêng thực. Trả về
    mean, các vector riêng đã xếp giảm theo trị riêng và tỉ lệ phương sai.
    """
    mean = features.mean(axis=0)
    centered = features - mean
    covariance = centered.T @ centered / (features.shape[0] - 1)

    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(-eigenvalues)
    eigenvalues = eigenvalues[order]
    components = eigenvectors[:, order]
    explained_ratio = eigenvalues / eigenvalues.sum()
    return {"mean": mean, "components": components, "explained_ratio": explained_ratio}


def pca_transform(features, model, n_components):
    """Chiếu dữ liệu lên n_components vector riêng đầu."""
    return (features - model["mean"]) @ model["components"][:, :n_components]


def lda_fit(features, target):
    """
    LDA bằng bài toán trị riêng tổng quát S_B w = lambda S_W w.

    Giải np.linalg.solve(S_W, S_B) thay vì nghịch đảo trực tiếp S_W để tránh
    nhân ma trận không cần thiết. Thêm một lượng nhỏ vào đường chéo S_W phòng
    trường hợp hiệp phương sai trong lớp suy biến. Vector riêng được chuẩn
    hoá độ dài 1; dấu tuỳ theo phân rã nên khi đối chiếu phải lấy trị tuyệt đối.
    """
    feature_count = features.shape[1]
    overall_mean = features.mean(axis=0)
    scatter_within = np.zeros((feature_count, feature_count))
    scatter_between = np.zeros((feature_count, feature_count))

    for class_label in np.unique(target):
        class_features = features[target == class_label]
        class_mean = class_features.mean(axis=0)
        centered = class_features - class_mean
        scatter_within += centered.T @ centered

        difference = (class_mean - overall_mean).reshape(feature_count, 1)
        scatter_between += class_features.shape[0] * (difference @ difference.T)

    ridge = 1e-8 * np.trace(scatter_within) / feature_count
    scatter_within += ridge * np.eye(feature_count)

    matrix = np.linalg.solve(scatter_within, scatter_between)
    eigenvalues, eigenvectors = np.linalg.eig(matrix)
    order = np.argsort(-np.real(eigenvalues))
    components = np.real(eigenvectors[:, order])

    for column in range(components.shape[1]):
        components[:, column] /= np.linalg.norm(components[:, column])

    return {"mean": overall_mean, "components": components}


def lda_transform(features, model, n_components):
    """Chiếu dữ liệu lên n_components hướng phân tách lớp đầu."""
    return (features - model["mean"]) @ model["components"][:, :n_components]


def nearest_centroid_accuracy(features, target):
    """
    Phân lớp đơn giản bằng tâm lớp trên không gian đã chiếu.

    Chỉ để so sánh khả năng giữ thông tin nhãn của PCA và LDA, không phải
    model chính của đồ án và không thay kết quả trên tập test thật.
    """
    classes = np.unique(target)
    centroids = np.array([features[target == label].mean(axis=0) for label in classes])
    distances = np.linalg.norm(features[:, None, :] - centroids[None, :, :], axis=2)
    predicted = classes[np.argmin(distances, axis=1)]
    return float(np.mean(predicted == target))


def subspace_cosine(left, right):
    """
    Độ khớp giữa hai cơ sở, bỏ qua dấu và thứ tự cột.

    Mỗi cột được chuẩn hoá độ dài 1 rồi lấy |cosin|. Một cột khớp hoàn toàn
    với một cột bên kia cho giá trị 1 dù sklearn chọn dấu ngược lại.
    """
    left_normalized = left / np.linalg.norm(left, axis=0)
    right_normalized = right / np.linalg.norm(right, axis=0)
    return np.abs(left_normalized.T @ right_normalized)


def main():
    print("=" * 68)
    print("PCA/LDA TU CAI - 004295 Chuong 4.4-4.5 (giam chieu)")
    print("=" * 68)

    features, target = make_demo_data(FROM_SCRATCH_SAMPLE_COUNT, FROM_SCRATCH_SEED)

    pca_model = pca_fit(features)
    sklearn_pca = PCA(n_components=2).fit(features)
    pca_ratio_error = float(np.max(np.abs(
        pca_model["explained_ratio"][:2] - sklearn_pca.explained_variance_ratio_
    )))

    print("\n[1] PCA tu cai doi chieu sklearn")
    print(f"    ty le phuong sai tu cai : {np.round(pca_model['explained_ratio'][:2], 4)}")
    print(f"    ty le phuong sai sklearn: {np.round(sklearn_pca.explained_variance_ratio_, 4)}")
    print(f"    sai so lon nhat         : {pca_ratio_error:.3e}")

    lda_model = lda_fit(features, target)
    sklearn_lda = LinearDiscriminantAnalysis(n_components=2).fit(features, target)
    alignment = subspace_cosine(
        lda_model["components"][:, :2], sklearn_lda.scalings_[:, :2]
    )
    lda_alignment = min(float(alignment.max(axis=0).min()), float(alignment.max(axis=1).min()))

    print("\n[2] LDA tu cai doi chieu sklearn")
    print(f"    do khop khong gian chieu : {lda_alignment:.6f} (1 la khop hoan toan)")
    print(f"    ghi chu: cosin lay tri tuyet doi vi dau vector rieng tuy y")

    pca_projected = pca_transform(features, pca_model, 2)
    lda_projected = lda_transform(features, lda_model, 2)
    pca_score = nearest_centroid_accuracy(pca_projected, target)
    lda_score = nearest_centroid_accuracy(lda_projected, target)

    print("\n[3] Hieu qua giam chieu (nearest centroid, 2 chieu)")
    print(f"    PCA khong dung nhan : do dung = {pca_score:.4f}")
    print(f"    LDA co dung nhan    : do dung = {lda_score:.4f}")
    print(f"    ghi chu: chi la tap demo, khong thay ket qua test cua model chinh")

    passed = pca_ratio_error < 1e-9 and lda_alignment > 0.999
    print("\n" + "=" * 68)
    print(f"TONG KET: {'DAT' if passed else 'SAI'} (PCA va LDA khop sklearn)")
    print("=" * 68)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
