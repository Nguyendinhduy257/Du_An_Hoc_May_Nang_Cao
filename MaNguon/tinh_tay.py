r"""
In các con số tính tay của Phụ lục A (khối B7.1-B7.3) để đối chiếu với mã.

Bài toán hai lớp của đồ án: review giả (CG, label_binary=1) là +1, review thật
(OR, label_binary=0) là -1. Sáu mẫu được chọn đúng quy tắc của đề: lấy 3 mẫu
+1 và 3 mẫu -1 từ tập huấn luyện bằng SEED = 2026 + G, duyệt xen kẽ +,-,+,-,+,-
và dùng hai đặc trưng có tiêu chí Fisher lớn nhất, đã chuẩn z-score trên train.

B7.1 một bước GD và một epoch PLA; B7.2 một bước thuận/ngược mạng 2-2-1;
B7.3 PCA và LDA trên chính sáu mẫu đó. Mọi số in ra làm tròn 4 chữ số để dán
thẳng vào báo cáo, nhưng phép tính bên trong vẫn dùng độ chính xác đầy đủ.

Chạy: python MaNGuon\tinh_tay.py
Không ghi đè file nào, không tham gia run_all.py.
"""

import atexit

import numpy as np
import pandas as pd

from cau_hinh_tinh_tay import GROUP_CODE, HAND_CALC_SEED
from config import LABEL_BINARY_COLUMN, TEXT_COLUMN, TRAIN_CSV_PATH
from don_rac import auto_cleanup

atexit.register(auto_cleanup)


def sigmoid(value):
    """Hàm logistic, dùng cho logistic regression và cho mạng 2-2-1."""
    return 1.0 / (1.0 + np.exp(-value))


def binary_cross_entropy(target, probability):
    """BCE trung bình; kẹp xác suất để tránh log(0)."""
    clipped = np.clip(probability, 1e-12, 1.0 - 1e-12)
    return float(-np.mean(
        target * np.log(clipped) + (1.0 - target) * np.log(1.0 - clipped)
    ))


def build_numeric_features(reviews):
    """
    Tập đặc trưng số ứng viên rút trực tiếp từ văn bản và điểm đánh giá.

    Đây là tập để chọn theo Fisher ở B7, không phải đặc trưng của model chính
    (model chính dùng TF-IDF). Chọn các đại lượng dễ giải thích bằng tay nên
    báo cáo có thể trình bày từng bước mà không cần chạy lại vectorizer.
    """
    texts = reviews[TEXT_COLUMN].astype(str)
    word_lists = texts.str.findall(r"[A-Za-z]+")

    return pd.DataFrame({
        "word_count": word_lists.map(len).astype(float),
        "char_count": texts.str.len().astype(float),
        "unique_word_ratio": word_lists.map(
            lambda words: len({word.lower() for word in words}) / max(1, len(words))
        ),
        "exclamation_count": texts.str.count("!").astype(float),
        "uppercase_ratio": texts.map(
            lambda text: sum(char.isupper() for char in text) / max(1, len(text))
        ),
        "avg_word_length": word_lists.map(
            lambda words: sum(len(word) for word in words) / max(1, len(words))
        ),
        "digit_count": texts.str.count(r"\d").astype(float),
        "rating": pd.to_numeric(reviews["rating"], errors="coerce").fillna(0.0),
        "has_link": texts.str.contains(
            r"https?://|www\.", case=False, regex=True
        ).astype(float),
    })


def fisher_scores(values, signed_target):
    """Fisher của từng cột: bình phương cách hai tâm chia cho tổng phương sai."""
    positive = values[signed_target == 1]
    negative = values[signed_target == -1]
    variance = positive.var(axis=0, ddof=1) + negative.var(axis=0, ddof=1)
    return (positive.mean(axis=0) - negative.mean(axis=0)) ** 2 / np.maximum(variance, 1e-12)


def select_features_and_samples():
    """Chọn hai đặc trưng Fisher lớn nhất rồi lấy sáu mẫu theo đúng đoạn mã của đề."""
    reviews = pd.read_csv(TRAIN_CSV_PATH, encoding="utf-8")
    signed_target = np.where(reviews[LABEL_BINARY_COLUMN].to_numpy() == 1, 1, -1)

    features = build_numeric_features(reviews)
    scores = fisher_scores(features.to_numpy(), signed_target)
    order = np.argsort(-scores)[:2]
    selected_names = [features.columns[index] for index in order]

    values = features.iloc[:, order].to_numpy()
    mean = values.mean(axis=0)
    std = np.where(values.std(axis=0) > 1e-12, values.std(axis=0), 1.0)
    standardized = (values - mean) / std

    rng = np.random.default_rng(HAND_CALC_SEED)
    positive_indices = np.flatnonzero(signed_target == 1)
    negative_indices = np.flatnonzero(signed_target != 1)
    positive_sample = rng.choice(positive_indices, 3, replace=False)
    negative_sample = rng.choice(negative_indices, 3, replace=False)
    indices = [
        positive_sample[0], negative_sample[0],
        positive_sample[1], negative_sample[1],
        positive_sample[2], negative_sample[2],
    ]

    return (
        standardized,
        signed_target,
        indices,
        selected_names,
        scores[order],
        reviews.iloc[indices]["text_"].tolist(),
    )


def logistic_one_step(features, binary_target):
    """Một bước GD full-batch cho hồi quy logistic: w0 = 0, eta = 0.1."""
    design = np.column_stack([np.ones(features.shape[0]), features])
    weights = np.zeros(3)
    learning_rate = 0.1

    probabilities = sigmoid(design @ weights)
    loss = binary_cross_entropy(binary_target, probabilities)
    gradient = design.T @ (probabilities - binary_target) / features.shape[0]
    new_weights = weights - learning_rate * gradient
    new_probabilities = sigmoid(design @ new_weights)
    new_loss = binary_cross_entropy(binary_target, new_probabilities)
    return probabilities, loss, gradient, new_weights, new_loss


def pla_one_epoch(features, signed_target):
    """Một epoch PLA theo thứ tự đã chọn; g = w.x, update khi y*g <= 0."""
    design = np.column_stack([np.ones(features.shape[0]), features])
    weights = np.zeros(3)
    steps = []

    for index in range(features.shape[0]):
        margin = float(design[index] @ weights)
        product = signed_target[index] * margin
        updated = product <= 0.0
        if updated:
            weights = weights + signed_target[index] * design[index]
        steps.append((margin, product, updated, weights.copy()))
    return steps


def mlp_one_step(features, binary_target):
    """Một bước thuận/ngược cho mạng 2-2-1 với khởi tạo và eta theo đề."""
    input_value = features[0]
    label = binary_target[0]
    weight_hidden = np.array([[0.2, -0.3], [0.4, 0.1]])
    bias_hidden = np.zeros(2)
    weight_output = np.array([0.5, -0.6])
    bias_output = 0.0

    hidden_input = weight_hidden @ input_value + bias_hidden
    hidden_output = sigmoid(hidden_input)
    output_input = float(weight_output @ hidden_output) + bias_output
    prediction = sigmoid(output_input)
    loss = binary_cross_entropy(np.array([label]), np.array([prediction]))

    error_output = prediction - label
    gradient_weight_output = error_output * hidden_output
    gradient_bias_output = error_output
    error_hidden = weight_output * error_output * hidden_output * (1.0 - hidden_output)
    gradient_weight_hidden = np.outer(error_hidden, input_value)
    gradient_bias_hidden = error_hidden

    learning_rate = 0.5
    new_weight_hidden = weight_hidden - learning_rate * gradient_weight_hidden
    new_bias_hidden = bias_hidden - learning_rate * gradient_bias_hidden
    new_weight_output = weight_output - learning_rate * gradient_weight_output
    new_bias_output = bias_output - learning_rate * gradient_bias_output

    new_hidden_output = sigmoid(new_weight_hidden @ input_value + new_bias_hidden)
    new_prediction = sigmoid(float(new_weight_output @ new_hidden_output) + new_bias_output)
    new_loss = binary_cross_entropy(np.array([label]), np.array([new_prediction]))

    # Kiểm chứng một đạo hàm bằng sai phân trung tâm cho dJ/dW1[0,0].
    epsilon = 1e-5

    def loss_at(candidate):
        hidden = sigmoid(np.array([[candidate, weight_hidden[0, 1]],
                                   [weight_hidden[1, 0], weight_hidden[1, 1]]]) @ input_value + bias_hidden)
        guess = sigmoid(float(weight_output @ hidden) + bias_output)
        return binary_cross_entropy(np.array([label]), np.array([guess]))

    numeric_gradient = (loss_at(weight_hidden[0, 0] + epsilon)
                        - loss_at(weight_hidden[0, 0] - epsilon)) / (2.0 * epsilon)

    return {
        "hidden_input": hidden_input,
        "hidden_output": hidden_output,
        "prediction": prediction,
        "loss": loss,
        "error_output": error_output,
        "error_hidden": error_hidden,
        "gradient_weight_hidden": gradient_weight_hidden,
        "gradient_bias_hidden": gradient_bias_hidden,
        "gradient_weight_output": gradient_weight_output,
        "gradient_bias_output": gradient_bias_output,
        "new_weight_hidden": new_weight_hidden,
        "new_bias_hidden": new_bias_hidden,
        "new_weight_output": new_weight_output,
        "new_bias_output": new_bias_output,
        "new_prediction": new_prediction,
        "new_loss": new_loss,
        "analytic_gradient": float(gradient_weight_hidden[0, 0]),
        "numeric_gradient": numeric_gradient,
    }


def pca_two_components(features):
    """PCA trên sáu mẫu x hai chiều, chia hiệp phương sai cho n - 1."""
    mean = features.mean(axis=0)
    centered = features - mean
    covariance = centered.T @ centered / (features.shape[0] - 1)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(-eigenvalues)
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    for column in range(eigenvectors.shape[1]):
        largest = np.argmax(np.abs(eigenvectors[:, column]))
        if eigenvectors[largest, column] < 0:
            eigenvectors[:, column] *= -1

    ratio = eigenvalues / eigenvalues.sum()
    first_projection = float(centered[0] @ eigenvectors[:, 0])
    return mean, covariance, eigenvalues, eigenvectors, ratio, first_projection


def lda_two_classes(features, signed_target):
    """LDA hai lớp: w chạy bằng S_W^{-1}(m+ - m-), chuẩn hoá ||w|| = 1."""
    positive = features[signed_target == 1]
    negative = features[signed_target == -1]
    mean_positive = positive.mean(axis=0)
    mean_negative = negative.mean(axis=0)

    scatter_within = np.zeros((features.shape[1], features.shape[1]))
    for group in (positive, negative):
        centered = group - group.mean(axis=0)
        scatter_within += centered.T @ centered

    determinant = np.linalg.det(scatter_within)
    note = ""
    if abs(determinant) < 1e-12:
        scatter_within += 1e-3 * np.eye(features.shape[1])
        note = "S_W suy biến, đã cộng 1e-3*I"

    direction = np.linalg.solve(scatter_within, mean_positive - mean_negative)
    direction = direction / np.linalg.norm(direction)
    raw_projections = features @ direction
    centered_projections = (features - features.mean(axis=0)) @ direction
    return mean_positive, mean_negative, scatter_within, direction, raw_projections, centered_projections, note


def main():
    print("=" * 68)
    print("TINH TAY DOI CHIEU - 004295 Phu luc A (B7.1-B7.3)")
    print(f"SEED = 2026 + G = {HAND_CALC_SEED} (G = {GROUP_CODE})")
    print("=" * 68)

    standardized, signed_target, indices, names, scores, texts = select_features_and_samples()
    features = standardized[indices]
    labels_signed = signed_target[indices]
    labels_binary = np.where(labels_signed == 1, 1.0, 0.0)

    print("\n[0] Chon dac trung va 6 mau")
    print(f"    hai dac trung Fisher lon nhat: {names[0]} ({scores[0]:.4f}), {names[1]} ({scores[1]:.4f})")
    for row in range(6):
        print(f"    mau {row + 1}: y={labels_signed[row]:+.0f}, chi so={indices[row]}, "
              f"x=({features[row, 0]:.4f}, {features[row, 1]:.4f})")
    print("    mau thu nhat (de B7.2): " + texts[0][:100])

    probabilities, loss, gradient, new_weights, new_loss = logistic_one_step(features, labels_binary)
    print("\n[B7.1a] Mot buoc GD full-batch (eta=0.1)")
    for row in range(6):
        print(f"    mau {row + 1}: y={labels_binary[row]:.0f}, yhat={probabilities[row]:.4f}")
    print(f"    J ban dau     : {loss:.4f}")
    print(f"    gradient      : [{gradient[0]:.4f}, {gradient[1]:.4f}, {gradient[2]:.4f}]")
    print(f"    w sau 1 buoc  : [{new_weights[0]:.4f}, {new_weights[1]:.4f}, {new_weights[2]:.4f}]")
    print(f"    J sau cap nhat: {new_loss:.4f}")

    print("\n[B7.1b] Mot epoch PLA (w0=0, thu tu +,-,+,-,+,-)")
    for row, (margin, product, updated, weights) in enumerate(pla_one_epoch(features, labels_signed), start=1):
        print(f"    buoc {row}: g={margin:.4f}, y*g={product:.4f}, "
              f"cap nhat={'co' if updated else 'khong'}, "
              f"w=({weights[0]:.4f}, {weights[1]:.4f}, {weights[2]:.4f})")

    mlp = mlp_one_step(features, labels_binary)
    print("\n[B7.2] Mot buoc thuan/nguoc mang 2-2-1 (mau dau tien, eta=0.5)")
    print(f"    z(1) = ({mlp['hidden_input'][0]:.4f}, {mlp['hidden_input'][1]:.4f})")
    print(f"    a(1) = ({mlp['hidden_output'][0]:.4f}, {mlp['hidden_output'][1]:.4f})")
    print(f"    yhat = {mlp['prediction']:.4f}, J = {mlp['loss']:.4f}")
    print(f"    delta(2) = {mlp['error_output']:.4f}")
    print(f"    delta(1) = ({mlp['error_hidden'][0]:.4f}, {mlp['error_hidden'][1]:.4f})")
    print(f"    grad W(1) = ({mlp['gradient_weight_hidden'][0, 0]:.4f}, {mlp['gradient_weight_hidden'][0, 1]:.4f}; "
          f"{mlp['gradient_weight_hidden'][1, 0]:.4f}, {mlp['gradient_weight_hidden'][1, 1]:.4f})")
    print(f"    grad b(1) = ({mlp['gradient_bias_hidden'][0]:.4f}, {mlp['gradient_bias_hidden'][1]:.4f})")
    print(f"    grad w(2) = ({mlp['gradient_weight_output'][0]:.4f}, {mlp['gradient_weight_output'][1]:.4f}), "
          f"grad b(2) = {mlp['gradient_bias_output']:.4f}")
    print(f"    W(1) moi = ({mlp['new_weight_hidden'][0, 0]:.4f}, {mlp['new_weight_hidden'][0, 1]:.4f}; "
          f"{mlp['new_weight_hidden'][1, 0]:.4f}, {mlp['new_weight_hidden'][1, 1]:.4f})")
    print(f"    w(2) moi = ({mlp['new_weight_output'][0]:.4f}, {mlp['new_weight_output'][1]:.4f}), "
          f"b(2) moi = {mlp['new_bias_output']:.4f}")
    print(f"    yhat moi = {mlp['new_prediction']:.4f}, J moi = {mlp['new_loss']:.4f}")
    print(f"    dao ham W(1)[0,0]: solution={mlp['analytic_gradient']:.6f}, "
          f"sai phan={mlp['numeric_gradient']:.6f}")

    mean, covariance, eigenvalues, eigenvectors, ratio, first_projection = pca_two_components(features)
    print("\n[B7.3a] PCA 6 mau x 2 dac trung")
    print(f"    vecto trung binh = ({mean[0]:.4f}, {mean[1]:.4f})")
    print(f"    hiep phuong sai = ({covariance[0, 0]:.4f}, {covariance[0, 1]:.4f}; "
          f"{covariance[1, 0]:.4f}, {covariance[1, 1]:.4f})")
    print(f"    tri rieng = ({eigenvalues[0]:.4f}, {eigenvalues[1]:.4f})")
    print(f"    vecto rieng 1 = ({eigenvectors[0, 0]:.4f}, {eigenvectors[1, 0]:.4f})")
    print(f"    vecto rieng 2 = ({eigenvectors[0, 1]:.4f}, {eigenvectors[1, 1]:.4f})")
    print(f"    ty le phuong sai = ({ratio[0]:.4f}, {ratio[1]:.4f})")
    print(f"    toa do mau dau tien = {first_projection:.4f}")

    mean_positive, mean_negative, scatter_within, direction, raw_projection, centered_projection, note = lda_two_classes(
        features, labels_signed
    )
    print("\n[B7.3b] LDA hai lop tren cung 6 mau")
    print(f"    m+ = ({mean_positive[0]:.4f}, {mean_positive[1]:.4f})")
    print(f"    m- = ({mean_negative[0]:.4f}, {mean_negative[1]:.4f})")
    print(f"    S_W = ({scatter_within[0, 0]:.4f}, {scatter_within[0, 1]:.4f}; "
          f"{scatter_within[1, 0]:.4f}, {scatter_within[1, 1]:.4f})")
    print(f"    w = ({direction[0]:.4f}, {direction[1]:.4f})")
    print("    chieu raw cua 6 mau: " + ", ".join(f"{value:.4f}" for value in raw_projection))
    print("    chieu tru trung binh: " + ", ".join(f"{value:.4f}" for value in centered_projection))
    if note:
        print(f"    ghi chu: {note}")

    print("\n" + "=" * 68)
    print("Het phan tinh tay. Doi chieu tung so voi code truoc khi vao Phu luc A.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
