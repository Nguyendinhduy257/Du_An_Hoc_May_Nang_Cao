r"""
Minh hoạ các thuật toán lõi của giáo trình bằng numpy thuần.

Nội dung: GD một biến và nhiều biến, momentum, SGD/mini-batch, quét tốc độ học
(CLO1); perceptron và Pocket (CLO2); MLP một tầng ẩn với lan truyền ngược,
gradient check, ba cấu hình và đối chứng MLPClassifier (CLO3). Đây là phần
minh hoạ, không tham gia huấn luyện model thật. Model thật nằm ở
train_baseline.py, dùng SGDClassifier của scikit-learn.

Dữ liệu sinh bằng numpy với seed cố định nên chạy lại cho cùng kết quả.
Chạy: python MaNguon\from_scratch.py
Mã thoát 0 nếu gradient check và bài XOR đều đạt.

Viết tắt dùng trong file:
    GD   - gradient descent (hạ gradient)
    SGD  - stochastic gradient descent (hạ gradient ngẫu nhiên)
    BCE  - binary cross-entropy (entropy chéo nhị phân)
    MLP  - multi-layer perceptron (mạng nơ-ron nhiều tầng)
    PLA  - perceptron learning algorithm
    CLO  - chuẩn đầu ra môn học
"""

import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPClassifier

from config import (
    FROM_SCRATCH_LEARNING_RATE,
    FROM_SCRATCH_SAMPLE_COUNT,
    FROM_SCRATCH_SEED,
    FROM_SCRATCH_STEPS,
    GRADIENT_CHECK_EPSILON,
    GRADIENT_CHECK_TOLERANCE,
)


# ------------------------------------------------------------------
# 1. Hồi quy tuyến tính: MSE và gradient
# ------------------------------------------------------------------

def add_bias_column(features):
    """Thêm cột 1 vào đầu X để hệ số chặn nằm chung vector trọng số."""
    sample_count = features.shape[0]
    ones = np.ones((sample_count, 1))
    return np.hstack([ones, features])


def mean_squared_error(weights, design, target):
    """MSE trung bình trên toàn bộ mẫu (dùng cho GD full-batch)."""
    residual = design @ weights - target
    return float(np.mean(residual * residual))


def mean_squared_error_gradient(weights, design, target):
    """Gradient của MSE: (2/n) * X^T (Xw - y)."""
    sample_count = design.shape[0]
    residual = design @ weights - target
    return (2.0 / sample_count) * (design.T @ residual)


def make_regression_data(sample_count, seed):
    """
    Sinh dữ liệu hồi quy 2 đặc trưng.

    Đặc trưng thứ hai cố ý có phương sai rất nhỏ (0.05) nên hướng gradient
    của nó yếu hơn hẳn. Nhờ vậy so sánh GD thường với momentum mới thấy
    khác biệt, chứ để hai đặc trưng cùng thang đo thì hai cách gần như nhau.
    """
    rng = np.random.default_rng(seed)

    feature_one = rng.normal(0.0, 1.0, sample_count)
    feature_two = rng.normal(0.0, 0.05, sample_count)
    noise = rng.normal(0.0, 0.05, sample_count)

    true_intercept = 1.5
    true_weight_one = 2.0
    true_weight_two = -3.0

    target = (
        true_intercept
        + true_weight_one * feature_one
        + true_weight_two * feature_two
        + noise
    )
    features = np.column_stack([feature_one, feature_two])
    return features, target


# ------------------------------------------------------------------
# 2. GD một biến, GD nhiều biến, momentum, SGD
# ------------------------------------------------------------------

def gradient_descent_one_variable(learning_rate, start, steps, tolerance):
    """
    Tối ưu f(x) = (x - 3)^2, có nghiệm giải tích x* = 3.

    Hàm này đạo hàm chỉ là 2(x - 3) nên kiểm tra bằng tay rất nhanh, dùng
    để thấy ảnh hưởng của learning rate trước khi chuyển sang bài nhiều biến.
    """
    position = float(start)
    losses = []

    for _ in range(steps):
        gradient = 2.0 * (position - 3.0)
        position = position - learning_rate * gradient
        loss = (position - 3.0) ** 2
        losses.append(loss)

        if loss < tolerance:
            break

    return position, losses


def gradient_descent(design, target, learning_rate, steps, tolerance):
    """GD full-batch cho hồi quy tuyến tính."""
    weights = np.zeros(design.shape[1])
    losses = []

    for _ in range(steps):
        gradient = mean_squared_error_gradient(weights, design, target)
        weights = weights - learning_rate * gradient

        loss = mean_squared_error(weights, design, target)
        losses.append(loss)

        if len(losses) >= 2 and abs(losses[-2] - losses[-1]) < tolerance:
            break

    return weights, losses


def gradient_descent_momentum(design, target, learning_rate, momentum, steps):
    """
    GD có quán tính: v = m*v - eta*grad; w = w + v (Ch1 tr. 32-37).

    Vận tốc cộng dồn qua các bước nên ở hướng gradient ổn định thì đi nhanh
    dần, còn ở hướng dao động thì các bước sau ngược dấu bớt lại.
    """
    weights = np.zeros(design.shape[1])
    velocity = np.zeros(design.shape[1])
    losses = []

    for _ in range(steps):
        gradient = mean_squared_error_gradient(weights, design, target)
        velocity = momentum * velocity - learning_rate * gradient
        weights = weights + velocity
        losses.append(mean_squared_error(weights, design, target))

    return weights, losses


def stochastic_gradient_descent(design, target, learning_rate, batch_size, steps, seed):
    """
    SGD / mini-batch: mỗi bước chỉ tính gradient trên một phần mẫu
    (Ch1 tr. 39-43).

    Với dữ liệu lớn, tính lại gradient trên toàn bộ mẫu sau mỗi bước là quá
    tốn, nên chia thành từng lô nhỏ. batch_size = n thì trùng với full-batch.
    """
    rng = np.random.default_rng(seed)
    sample_count = design.shape[0]
    weights = np.zeros(design.shape[1])
    losses = []

    for _ in range(steps):
        order = rng.permutation(sample_count)

        for start in range(0, sample_count, batch_size):
            batch_index = order[start:start + batch_size]
            batch_design = design[batch_index]
            batch_target = target[batch_index]
            gradient = mean_squared_error_gradient(weights, batch_design, batch_target)
            weights = weights - learning_rate * gradient

        losses.append(mean_squared_error(weights, design, target))

    return weights, losses


# ------------------------------------------------------------------
# 3. Sigmoid, BCE, gradient check
# ------------------------------------------------------------------

def sigmoid(value):
    """Hàm sigmoid 1 / (1 + e^-z), kẹp z để exp không tràn số."""
    clipped = np.clip(value, -500.0, 500.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def binary_cross_entropy(target, probability):
    """BCE trung bình; kẹp xác suất để log(0) không xảy ra."""
    clipped = np.clip(probability, 1e-12, 1.0 - 1e-12)
    return float(-np.mean(target * np.log(clipped) + (1.0 - target) * np.log(1.0 - clipped)))


def logistic_loss(weights, design, target):
    """BCE của hồi quy logistic, dùng làm hàm mục tiêu khi kiểm tra gradient."""
    probability = sigmoid(design @ weights)
    return binary_cross_entropy(target, probability)


def logistic_gradient(weights, design, target):
    """
    Gradient của BCE theo trọng số: X^T (a - y) / n.

    Đạo hàm sigmoid nhân với đạo hàm BCE triệt tiêu nhau, còn lại đúng
    dJ/dz = a - y (Ch3 phần 2 tr. 10), nên công thức ngắn hơn vẻ ngoài.
    """
    sample_count = design.shape[0]
    probability = sigmoid(design @ weights)
    return design.T @ (probability - target) / sample_count


def gradient_check(analytic_function, weights, design, target, epsilon):
    """
    So gradient giải tích với gradient sai phân trung tâm.

    Sai phân trung tâm có sai số O(eps^2) nên đủ chính xác để phát hiện công
    thức đạo hàm viết sai. Trả về sai số tương đối lớn nhất trên mọi thành
    phần của vector trọng số.
    """
    analytic = analytic_function(weights, design, target)
    numeric = np.zeros_like(weights)

    for index in range(weights.shape[0]):
        original = weights[index]

        weights[index] = original + epsilon
        loss_plus = logistic_loss(weights, design, target)

        weights[index] = original - epsilon
        loss_minus = logistic_loss(weights, design, target)

        weights[index] = original
        numeric[index] = (loss_plus - loss_minus) / (2.0 * epsilon)

    denominator = np.maximum(1e-12, np.abs(analytic) + np.abs(numeric))
    relative_error = np.abs(analytic - numeric) / denominator
    return float(np.max(relative_error))


def make_classification_data(sample_count, seed, spread=0.5):
    """
    Sinh hai cụm Gauss 2 chiều: nhãn 0 = thật, nhãn 1 = giả.

    Với spread nhỏ hai cụm gần tách được tuyến tính, PLA hội tụ theo định lý
    Novikoff (Ch2 phần 2). Tăng spread để tạo dữ liệu chồng lấn; khi đó PLA
    không còn hội tụ và cần Pocket giữ lại nghiệm tốt nhất.
    """
    rng = np.random.default_rng(seed)
    per_class = sample_count // 2

    real_features = rng.normal([-2.0, -2.0], spread, size=(per_class, 2))
    fake_features = rng.normal([2.0, 2.0], spread, size=(per_class, 2))

    features = np.vstack([real_features, fake_features])
    target = np.concatenate([np.zeros(per_class), np.ones(per_class)])
    return features, target


def logistic_regression_fit(design, target, learning_rate, steps):
    """Huấn luyện hồi quy logistic bằng GD full-batch, trả trọng số và loss."""
    weights = np.zeros(design.shape[1])
    losses = []

    for _ in range(steps):
        gradient = logistic_gradient(weights, design, target)
        weights = weights - learning_rate * gradient
        losses.append(logistic_loss(weights, design, target))

    return weights, losses


def accuracy(weights, design, target):
    """Tỉ lệ dự đoán đúng với ngưỡng 0.5."""
    probability = sigmoid(design @ weights)
    predicted = (probability >= 0.5).astype(float)
    return float(np.mean(predicted == target))


# ------------------------------------------------------------------
# 4. Perceptron (CLO2)
# ------------------------------------------------------------------

def perceptron_fit(features, target, learning_rate, steps, seed):
    """
    Perceptron (PLA): duyệt mẫu theo thứ tự ngẫu nhiên, sửa trọng số khi
    phân loại sai.

    Công thức cập nhật w <- w + eta*y*x chỉ đúng khi y là +1/-1, nên phải
    đổi nhãn 0/1 sang +1/-1 trước khi tính.
    """
    rng = np.random.default_rng(seed)
    design = add_bias_column(features)
    signed_target = np.where(target > 0.0, 1.0, -1.0)
    weights = np.zeros(design.shape[1])
    mistake_counts = []

    for _ in range(steps):
        order = rng.permutation(design.shape[0])
        mistakes = 0

        for index in order:
            margin = signed_target[index] * (design[index] @ weights)
            if margin <= 0.0:
                weights = weights + learning_rate * signed_target[index] * design[index]
                mistakes += 1

        mistake_counts.append(mistakes)
        if mistakes == 0:
            break

    return weights, mistake_counts


def perceptron_accuracy(weights, features, target):
    """Tỉ lệ đúng của perceptron; dấu của z quyết định nhãn."""
    design = add_bias_column(features)
    signed_target = np.where(target > 0.0, 1.0, -1.0)
    predicted_sign = np.where(design @ weights >= 0.0, 1.0, -1.0)
    return float(np.mean(predicted_sign == signed_target))


def perceptron_mistake_count(weights, features, target):
    """Đếm số mẫu bị PLA phân sai với trọng số hiện tại."""
    design = add_bias_column(features)
    signed_target = np.where(target > 0.0, 1.0, -1.0)
    predicted_sign = np.where(design @ weights >= 0.0, 1.0, -1.0)
    return int(np.sum(predicted_sign != signed_target))


def pocket_fit(features, target, learning_rate, steps, seed):
    """
    Pocket: gi lại trọng số có ít lỗi nhất từng xuất hiện trong lúc huấn luyện.

    PLA cập nhật rồi lấy trọng số cuối cùng; trên dữ liệu chồng lấn trọng số
    đó có thể tệ hơn một nghiệm đã gặp ở vòng trước. Sau mỗi vòng, Pocket đếm
    lại toàn bộ tập và chỉ thay nghiệm tốt khi số lỗi giảm.
    """
    rng = np.random.default_rng(seed)
    design = add_bias_column(features)
    signed_target = np.where(target > 0.0, 1.0, -1.0)
    weights = np.zeros(design.shape[1])
    best_weights = weights.copy()
    best_mistakes = perceptron_mistake_count(weights, features, target)
    mistake_counts = []

    for _ in range(steps):
        order = rng.permutation(design.shape[0])
        mistakes = 0

        for index in order:
            margin = signed_target[index] * (design[index] @ weights)
            if margin <= 0.0:
                weights = weights + learning_rate * signed_target[index] * design[index]
                mistakes += 1

        total_mistakes = perceptron_mistake_count(weights, features, target)
        mistake_counts.append(total_mistakes)
        if total_mistakes < best_mistakes:
            best_mistakes = total_mistakes
            best_weights = weights.copy()

        if mistakes == 0:
            break

    return best_weights, best_mistakes, mistake_counts


# ------------------------------------------------------------------
# 5. MLP một tầng ẩn + lan truyền ngược (CLO3)
# ------------------------------------------------------------------

def make_mlp_parameters(input_size, hidden_size, seed):
    """Khởi tạo trọng số nhỏ ngẫu nhiên; bias bằng 0."""
    rng = np.random.default_rng(seed)
    return {
        "weight_hidden": rng.normal(0.0, 0.5, (hidden_size, input_size)),
        "bias_hidden": np.zeros(hidden_size),
        "weight_output": rng.normal(0.0, 0.5, (1, hidden_size)),
        "bias_output": np.zeros(1),
    }


def mlp_forward(parameters, features):
    """Lan truyền thuận, trả xác suất và cache cho bước ngược."""
    hidden_input = features @ parameters["weight_hidden"].T + parameters["bias_hidden"]
    hidden_output = sigmoid(hidden_input)

    output_input = hidden_output @ parameters["weight_output"].T + parameters["bias_output"]
    output = sigmoid(output_input)

    cache = {
        "features": features,
        "hidden_output": hidden_output,
        "output": output,
    }
    return output, cache


def mlp_loss(parameters, features, target):
    """BCE của MLP, dùng cho gradient check."""
    output, _ = mlp_forward(parameters, features)
    return binary_cross_entropy(target, output)


def mlp_backward(parameters, cache, target):
    """
    Lan truyền ngược cho MLP 1 tầng ẩn với sigmoid + BCE.

    Với sigmoid + BCE thì dJ/dz2 = a - y (Ch3 phần 2 tr. 10), nên tầng ra
    không cần nhân thêm đạo hàm sigmoid. Tầng ẩn thì vẫn phải nhân
    a1*(1 - a1) như bình thường.
    """
    features = cache["features"]
    hidden_output = cache["hidden_output"]
    output = cache["output"]
    sample_count = features.shape[0]

    output_error = output - target
    weight_output_gradient = output_error.T @ hidden_output / sample_count
    bias_output_gradient = np.mean(output_error, axis=0)

    hidden_error = (output_error @ parameters["weight_output"]) * hidden_output * (1.0 - hidden_output)
    weight_hidden_gradient = hidden_error.T @ features / sample_count
    bias_hidden_gradient = np.mean(hidden_error, axis=0)

    return {
        "weight_hidden": weight_hidden_gradient,
        "bias_hidden": bias_hidden_gradient,
        "weight_output": weight_output_gradient,
        "bias_output": bias_output_gradient,
    }


def mlp_fit(features, target, hidden_size, learning_rate, steps, seed):
    """Huấn luyện MLP bằng GD full-batch."""
    parameters = make_mlp_parameters(features.shape[1], hidden_size, seed)
    losses = []

    for _ in range(steps):
        output, cache = mlp_forward(parameters, features)
        gradients = mlp_backward(parameters, cache, target)

        for name in parameters:
            parameters[name] = parameters[name] - learning_rate * gradients[name]

        losses.append(binary_cross_entropy(target, output))

    return parameters, losses


def mlp_gradient_check(parameters, features, target, epsilon):
    """
    Kiểm tra gradient lan truyền ngược bằng sai phân trên từng tham số.

    Một lỗi dấu hoặc lỗi hoán vị trong backprop vẫn có thể cho mạng "học
    được" nhưng học sai; gradient check phát hiện ngay chỗ đó.
    """
    _, cache = mlp_forward(parameters, features)
    analytic = mlp_backward(parameters, cache, target)
    max_relative_error = 0.0

    for name, value in parameters.items():
        numeric = np.zeros_like(value)

        for index in np.ndindex(value.shape):
            original = value[index]

            value[index] = original + epsilon
            loss_plus = mlp_loss(parameters, features, target)

            value[index] = original - epsilon
            loss_minus = mlp_loss(parameters, features, target)

            value[index] = original
            numeric[index] = (loss_plus - loss_minus) / (2.0 * epsilon)

        denominator = np.maximum(1e-12, np.abs(numeric) + np.abs(analytic[name]))
        relative_error = np.abs(numeric - analytic[name]) / denominator
        max_relative_error = max(max_relative_error, float(np.max(relative_error)))

    return max_relative_error


def make_xor_data():
    """
    Bài toán XOR, dùng để chứng minh vì sao cần tầng ẩn.

    Không có siêu phẳng nào tách được XOR, nên perceptron và hồi quy logistic
    phải thất bại, còn MLP một tầng ẩn thì học được.
    """
    features = np.array(
        [
            [0.0, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
            [1.0, 1.0],
        ]
    )
    target = np.array([[0.0], [1.0], [1.0], [0.0]])
    return features, target


def mlp_accuracy(parameters, features, target):
    """Tỉ lệ đúng của MLP với ngưỡng 0.5."""
    output, _ = mlp_forward(parameters, features)
    predicted = (output >= 0.5).astype(float)
    return float(np.mean(predicted == target))


# ------------------------------------------------------------------
# 6. Chạy tất cả và in báo cáo
# ------------------------------------------------------------------

def main():
    results = {}

    print("=" * 68)
    print("MINH HOẠ FROM-SCRATCH - neo giáo trình Học máy nâng cao")
    print("=" * 68)

    # GD một biến
    position, losses_one = gradient_descent_one_variable(
        FROM_SCRATCH_LEARNING_RATE, 0.0, FROM_SCRATCH_STEPS, 1e-12
    )
    print("\n[1] GD một biến: f(x) = (x - 3)^2")
    print(f"    x sau {len(losses_one):>3} bước : {position:.6f}")
    print(f"    nghiệm giải tích      : 3.000000")
    print(f"    loss cuối             : {losses_one[-1]:.3e}")
    results["gd_one_variable_final_x"] = round(position, 6)

    # GD nhiều biến
    features, target = make_regression_data(FROM_SCRATCH_SAMPLE_COUNT, FROM_SCRATCH_SEED)
    design = add_bias_column(features)

    weights, losses_multi = gradient_descent(
        design, target, FROM_SCRATCH_LEARNING_RATE, FROM_SCRATCH_STEPS, 1e-14
    )
    reference, _, _, _ = np.linalg.lstsq(design, target, rcond=None)

    print("\n[2] GD nhiều biến: hồi quy tuyến tính 2 đặc trưng")
    print(f"    trọng số GD           : {np.round(weights, 4)}")
    print(f"    nghiệm bình phương tối thiểu: {np.round(reference, 4)}")
    print(f"    MSE cuối             : {losses_multi[-1]:.6f}")
    print("    ghi chú: trọng số thứ ba còn xa nghiệm vì đặc trưng 2 có thang đo")
    print("             nhỏ, gradient theo hướng đó nhỏ; đây là lý do cần momentum.")
    results["gd_multi_final_loss"] = round(losses_multi[-1], 6)

    # Momentum so với GD thường
    weights_momentum, losses_momentum = gradient_descent_momentum(
        design, target, FROM_SCRATCH_LEARNING_RATE, 0.9, FROM_SCRATCH_STEPS
    )
    print("\n[3] Momentum so với GD thường (cùng số bước)")
    print(f"    loss GD thường        : {losses_multi[-1]:.6f}")
    print(f"    loss momentum         : {losses_momentum[-1]:.6f}")
    results["gd_plain_loss"] = round(losses_multi[-1], 6)
    results["gd_momentum_loss"] = round(losses_momentum[-1], 6)

    # SGD / mini-batch
    print("\n[4] SGD / mini-batch (cùng số epoch)")
    for batch_size in (1, 16, FROM_SCRATCH_SAMPLE_COUNT):
        _, losses_sgd = stochastic_gradient_descent(
            design, target, FROM_SCRATCH_LEARNING_RATE, batch_size,
            FROM_SCRATCH_STEPS, FROM_SCRATCH_SEED
        )
        label = "full-batch" if batch_size == FROM_SCRATCH_SAMPLE_COUNT else f"batch {batch_size}"
        print(f"    {label:<12}: loss cuối = {losses_sgd[-1]:.6f}")
        results[f"sgd_loss_batch_{batch_size}"] = round(losses_sgd[-1], 6)

    # Quét tốc độ học: ít nhất bốn giá trị eta cho cùng một bài toán.
    print("\n[5] Quét tốc độ học eta (GD full-batch, cùng số bước)")
    for learning_rate in (0.01, 0.03, 0.1, 0.3, 0.5):
        _, learning_losses = gradient_descent(
            design, target, learning_rate, FROM_SCRATCH_STEPS, 1e-14
        )
        print(f"    eta = {learning_rate:<5}: loss cuối = {learning_losses[-1]:.6f}")
        results[f"gd_loss_eta_{learning_rate}"] = round(learning_losses[-1], 6)

    # Gradient check hồi quy logistic
    class_features, class_target = make_classification_data(
        FROM_SCRATCH_SAMPLE_COUNT, FROM_SCRATCH_SEED
    )
    class_design = add_bias_column(class_features)
    logistic_weights = np.array([0.2, -0.4, 0.3])

    logistic_error = gradient_check(
        logistic_gradient, logistic_weights, class_design, class_target,
        GRADIENT_CHECK_EPSILON
    )
    print("\n[6] Gradient check hồi quy logistic")
    print(f"    sai số tương đối lớn nhất: {logistic_error:.3e}")
    print(f"    ngưỡng chấp nhận         : {GRADIENT_CHECK_TOLERANCE:.0e}")
    results["logistic_gradient_error"] = logistic_error

    # Gradient check MLP
    xor_features, xor_target = make_xor_data()
    mlp_parameters = make_mlp_parameters(2, 3, FROM_SCRATCH_SEED)
    mlp_error = mlp_gradient_check(
        mlp_parameters, xor_features, xor_target, GRADIENT_CHECK_EPSILON
    )
    print("\n[7] Gradient check MLP 1 tầng ẩn (3 nút ẩn)")
    print(f"    sai số tương đối lớn nhất: {mlp_error:.3e}")
    results["mlp_gradient_error"] = mlp_error

    # Perceptron
    perceptron_weights, mistake_counts = perceptron_fit(
        class_features, class_target, 1.0, FROM_SCRATCH_STEPS, FROM_SCRATCH_SEED
    )
    perceptron_score = perceptron_accuracy(perceptron_weights, class_features, class_target)
    print("\n[8] Perceptron (PLA) - CLO2")
    print(f"    số vòng cần            : {len(mistake_counts)}")
    print(f"    lỗi ở vòng cuối        : {mistake_counts[-1]}")
    print(f"    độ chính xác           : {perceptron_score:.4f}")
    results["perceptron_accuracy"] = round(perceptron_score, 4)

    # Pocket trên dữ liệu chồng lấn: PLA không hội tụ, cần gi nghiệm tốt nhất.
    overlap_features, overlap_target = make_classification_data(
        FROM_SCRATCH_SAMPLE_COUNT, FROM_SCRATCH_SEED + 1, spread=1.6
    )
    pla_overlap_weights, pla_overlap_counts = perceptron_fit(
        overlap_features, overlap_target, 1.0, FROM_SCRATCH_STEPS, FROM_SCRATCH_SEED
    )
    pla_overlap_mistakes = perceptron_mistake_count(
        pla_overlap_weights, overlap_features, overlap_target
    )
    pocket_weights, pocket_mistakes, pocket_counts = pocket_fit(
        overlap_features, overlap_target, 1.0, FROM_SCRATCH_STEPS, FROM_SCRATCH_SEED
    )
    pocket_score = perceptron_accuracy(pocket_weights, overlap_features, overlap_target)
    print("\n[9] Pocket so với PLA trên dữ liệu chồng lấn - CLO2")
    print(f"    PLA lỗi ở vòng cuối    : {pla_overlap_mistakes}")
    print(f"    Pocket lỗi tốt nhất    : {pocket_mistakes}")
    print(f"    PLA / Pocket độ đúng   : {perceptron_accuracy(pla_overlap_weights, overlap_features, overlap_target):.4f} / {pocket_score:.4f}")
    results["pla_overlap_mistakes"] = pla_overlap_mistakes
    results["pocket_best_mistakes"] = pocket_mistakes
    results["pocket_accuracy"] = round(pocket_score, 4)

    # MLP trên XOR
    xor_parameters, xor_losses = mlp_fit(
        xor_features, xor_target, 4, 2.0, 5000, FROM_SCRATCH_SEED
    )
    xor_score = mlp_accuracy(xor_parameters, xor_features, xor_target)
    print("\n[10] MLP trên XOR - CLO3")
    print(f"    loss cuối              : {xor_losses[-1]:.6f}")
    print(f"    độ chính xác           : {xor_score:.4f}")
    results["mlp_xor_accuracy"] = round(xor_score, 4)

    # Ba cấu hình MLP trên cùng dữ liệu chồng lấn: đổi số nút ẩn và eta.
    overlap_target_2d = overlap_target.reshape(-1, 1)
    mlp_configs = ((2, 0.5), (8, 0.5), (4, 2.0))
    print("\n[11] Ba cấu hình MLP tự cài (dữ liệu chồng lấn, 3000 bước)")
    for hidden_size, mlp_learning_rate in mlp_configs:
        config_parameters, config_losses = mlp_fit(
            overlap_features, overlap_target_2d, hidden_size,
            mlp_learning_rate, 3000, FROM_SCRATCH_SEED
        )
        config_score = mlp_accuracy(config_parameters, overlap_features, overlap_target_2d)
        print(f"    ẩn={hidden_size}, eta={mlp_learning_rate:<4}: loss={config_losses[-1]:.6f}, độ đúng={config_score:.4f}")
        results[f"mlp_hidden_{hidden_size}_eta_{mlp_learning_rate}_accuracy"] = round(config_score, 4)

    # Đối chứng: cùng kiến trúc, activation, full-batch, không momentum. sklearn
    # dùng momentum 0.9 mặc định nên phải tắt đi để so sánh công bằng.
    print("\n[12] Đối chứng sklearn MLPClassifier (cùng cấu hình, không momentum)")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        for hidden_size, mlp_learning_rate in mlp_configs:
            sklearn_mlp = MLPClassifier(
                hidden_layer_sizes=(hidden_size,),
                activation="logistic",
                solver="sgd",
                momentum=0,
                nesterovs_momentum=False,
                learning_rate_init=mlp_learning_rate,
                batch_size=FROM_SCRATCH_SAMPLE_COUNT,
                max_iter=3000,
                tol=1e-8,
                random_state=FROM_SCRATCH_SEED,
            )
            sklearn_mlp.fit(overlap_features, overlap_target)
            sklearn_score = sklearn_mlp.score(overlap_features, overlap_target)
            print(f"    ẩn={hidden_size}, eta={mlp_learning_rate:<4}: loss={float(sklearn_mlp.loss_):.6f}, độ đúng={sklearn_score:.4f}")
            results[f"sklearn_mlp_hidden_{hidden_size}_eta_{mlp_learning_rate}_accuracy"] = round(sklearn_score, 4)

    # Tổng kết
    logistic_pass = logistic_error < GRADIENT_CHECK_TOLERANCE
    mlp_pass = mlp_error < GRADIENT_CHECK_TOLERANCE
    xor_pass = xor_score >= 0.99

    print("\n" + "=" * 68)
    print("TỔNG KẾT")
    print(f"    gradient check logistic : {'ĐẠT' if logistic_pass else 'SAI'}")
    print(f"    gradient check MLP      : {'ĐẠT' if mlp_pass else 'SAI'}")
    print(f"    MLP học XOR             : {'ĐẠT' if xor_pass else 'SAI'}")
    print("=" * 68)

    all_pass = logistic_pass and mlp_pass and xor_pass
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
