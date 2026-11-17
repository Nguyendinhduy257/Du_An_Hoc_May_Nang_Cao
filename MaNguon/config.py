r"""
Cấu hình dùng chung của cả đồ án.

Đường dẫn thư mục, tham số model, giới hạn tải file và thông tin PostgreSQL
đều đặt ở đây. Các module khác import lại, không tự khai báo hằng số riêng,
nhờ vậy sửa một chỗ là cả pipeline đổi theo.

File này không chạy trực tiếp.
"""

from pathlib import Path

# Gốc dự án, suy ra từ vị trí file này (MaNguon/config.py lên một cấp) để mở
# terminal ở thư mục nào cũng chạy được, không ghi cứng đường dẫn ổ D:.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Thư mục gốc của từng nhóm ----------------------------------------------
# Gom về một chỗ để người mới đọc là biết mỗi loại tệp nằm đâu. Các file khác
# không được tự ghép đường dẫn bằng "..".
DATA_DIR = PROJECT_ROOT / "DuLieuDeHoc"
RAW_DATA_DIR = DATA_DIR / "DuLieuTho"
PROCESSED_DIR = DATA_DIR / "DuLieuDaXuLy"
RESULTS_DIR = PROJECT_ROOT / "KetQuaChay"
WEB_DIR = PROJECT_ROOT / "Web"
DEMO_DATA_DIR = PROJECT_ROOT / "DuLieuDemo"
MODELS_DIR = PROJECT_ROOT / "MoHinh"
BACKUP_DIR = PROJECT_ROOT / "SaoLuu"
DEPLOY_DIR = PROJECT_ROOT / "ThuMucChienKhai"

# --- Đường dẫn dữ liệu -------------------------------------------------------
RAW_CSV_PATH = RAW_DATA_DIR / "fake reviews dataset.csv"

TRAIN_CSV_PATH = PROCESSED_DIR / "train.csv"
VAL_CSV_PATH = PROCESSED_DIR / "val.csv"
TEST_CSV_PATH = PROCESSED_DIR / "test.csv"

# --- Đường dẫn báo cáo -------------------------------------------------------
METRICS_JSON_PATH = RESULTS_DIR / "baseline_metrics.json"

# Bản số liệu trước khi hiệu chuẩn, giữ lại để so sánh. Hiệu chuẩn làm đổi cả
# xác suất lẫn ngưỡng, muốn nói "tốt hơn" thì phải còn số cũ mà đối chiếu.
METRICS_JSON_V1_PATH = RESULTS_DIR / "baseline_metrics_v1.json"

# Kết quả đo chất lượng các luật phân nhóm (không phải nhãn ground truth).
HEURISTIC_AUDIT_JSON_PATH = RESULTS_DIR / "heuristic_audit.json"

# Kết quả đo độ lệch do dịch máy (dịch vòng Việt -> Anh).
TRANSLATION_BIAS_JSON_PATH = RESULTS_DIR / "translation_bias.json"

# So sánh model chính với hai baseline đơn giản: đoán lớp đa số và hồi quy
# logistic ngưỡng 0,5. Khai báo ở đây vì run_all.py cần biết báo cáo nào phải
# sinh lại, không để đường dẫn nằm rải trong từng script.
BASELINE_COMPARISON_JSON_PATH = RESULTS_DIR / "baseline_comparison.json"

# Bảng chi phí theo từng ngưỡng (dùng COST_FALSE_POSITIVE / COST_FALSE_NEGATIVE).
THRESHOLD_COST_JSON_PATH = RESULTS_DIR / "threshold_cost_table.json"

# Số review lấy mẫu khi đo độ lệch dịch máy. Mỗi review tốn hai lượt gọi dịch
# (Anh -> Việt -> Anh) nên 30 review là 60 request: đủ thấy xu hướng mà không
# chạy quá lâu.
TRANSLATION_BIAS_SAMPLE_SIZE = 30

# Dự đoán từng review, sinh ra trong cùng lần chạy train_baseline.py. Lớp web
# cần hai file này để vẽ biểu đồ phân bố xác suất và bảng review mẫu, nhưng
# không được train lại, tránh sinh ra hai bộ số liệu lệch nhau.
TEST_PREDICTIONS_CSV_PATH = RESULTS_DIR / "test_predictions.csv"
VAL_PREDICTIONS_CSV_PATH = RESULTS_DIR / "val_predictions.csv"

# --- Đường dẫn web -----------------------------------------------------------
# Mã giao diện và dữ liệu hiển thị nằm ở hai thư mục:
#   Web/        : index.html, style.css, app.js - chỉ mã giao diện.
#   DuLieuDemo/ : data_meta.js, data_reviews.js - dữ liệu sinh tự động.
# Tách ra để sửa giao diện không đụng dữ liệu và ngược lại; nhìn đường dẫn là
# biết file nào do máy sinh.
#
# Dữ liệu web chia làm hai file: data_meta.js nhẹ, đủ để hiện khung trang;
# data_reviews.js hơn 4 MB, chỉ cần khi kéo xuống bảng review. Gộp lại thì
# trang mở chậm. Đuôi .js chứ không phải .json vì mở bằng file:// thì fetch()
# bị chặn, còn thẻ <script src> vẫn nạp được.
WEB_META_PATH = DEMO_DATA_DIR / "data_meta.js"
WEB_REVIEWS_PATH = DEMO_DATA_DIR / "data_reviews.js"

# --- Notebook minh hoạ -------------------------------------------------------
# run_all.py cần biết file nào phải chạy lại. Notebook/ nằm ngoài MaNguon/ nên
# không suy ra được từ vị trí file mã nguồn.
NOTEBOOK_DIR = PROJECT_ROOT / "Notebook"
NOTEBOOK_PATH = NOTEBOOK_DIR / "from_scratch_gd_lr.ipynb"

# --- Model đã lưu ------------------------------------------------------------
# API phải dự đoán câu mới mà không huấn luyện lại mỗi lần gọi.
MODEL_PATH = MODELS_DIR / "baseline_lr_tfidf.pkl"

# --- API dự đoán -------------------------------------------------------------
# Chỉ nghe trên 127.0.0.1 (localhost) nên máy khác trong mạng không vào được.
# Đây là demo không có xác thực, mở 0.0.0.0 là rủi ro không cần thiết.
API_HOST = "127.0.0.1"
API_PORT = 8000

# Chặn câu nhập tay quá dài làm chậm server.
MAX_INPUT_CHARS = 5000

# Tỷ lệ tối thiểu token (từ/cụm từ) phải có trong từ vựng model. Dùng tỷ lệ
# thay vì số tuyệt đối vì câu 200 từ mà chỉ 1 từ quen vẫn là câu xa lạ. Câu
# dưới ngưỡng bị gắn cờ low_confidence và không tính là hữu ích.
MIN_KNOWN_TOKEN_RATIO = 0.30

# --- Dịch tự động sang tiếng Anh ---------------------------------------------
# Bật/tắt bước dịch trước khi dự đoán.
TRANSLATE_ENABLED = True

# Chặn trường hợp mạng chậm hoặc bị chặn làm treo server.
TRANSLATE_TIMEOUT_SECONDS = 8

# Endpoint công khai hay chập chờn; thử lại để file lớn không mất dịch chỉ vì
# một request lỗi tạm thời.
TRANSLATE_MAX_ATTEMPTS = 3

# Thời gian chờ giữa hai lần thử (giây), tăng dần theo số lần đã thử.
TRANSLATE_RETRY_DELAY_SECONDS = 0.6

# Ba địa chỉ dịch, thử theo thứ tự. Dịch vụ công khai không chính thức có thể
# chặn một tên miền trong khi tên miền khác vẫn chạy.
TRANSLATE_GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
TRANSLATE_GOOGLE_ALT_URL = "https://clients5.google.com/translate_a/t"
TRANSLATE_MYMEMORY_URL = "https://api.mymemory.translated.net/get"

# Tên nhà cung cấp lưu vào bảng translation_cache để biết bản dịch đến từ đâu.
TRANSLATION_PROVIDER_GOOGLE = "google-unofficial"
TRANSLATION_PROVIDER_GOOGLE_ALT = "google-clients5"
TRANSLATION_PROVIDER_MYMEMORY = "mymemory"

# Biên "sát ngưỡng" cho câu đã qua dịch máy. Dịch máy làm văn bản giống văn máy
# sinh và đẩy xác suất giả lên; nếu chỉ chênh ngưỡng trong khoảng này thì kết
# luận có thể đổi chỉ vì bước dịch, nên không giữ làm review hữu ích.
TRANSLATION_BORDERLINE_MARGIN = 0.08

# Ngưỡng tương đồng tối thiểu khi dịch vòng (gốc -> Anh -> gốc). Bản dịch vòng
# khác câu gốc quá nhiều nghĩa là đã sai nghĩa, xác suất đọc được không còn
# đáng tin.
TRANSLATION_CONSISTENCY_MIN_SIMILARITY = 0.55

# Chỉ so tối đa 2.000 ký tự đầu; so chuỗi rất dài tốn thời gian mà phần đầu đã
# đủ đại diện.
TRANSLATION_CONSISTENCY_MAX_CHARS = 2000

# --- Hiệu chuẩn xác suất (Platt scaling) -------------------------------------
# SGDClassifier cho điểm số đúng thứ tự nhưng chưa phải xác suất thật. Platt
# scaling fit một hàm logistic một biến trên tập val để kéo điểm số về đúng
# tần suất thực nghiệm; kiểm chứng bằng Brier score.
CALIBRATION_EPSILON = 1e-6

# Số khoảng chia khi vẽ biểu đồ độ tin cậy của xác suất.
RELIABILITY_BIN_COUNT = 10

# --- PostgreSQL --------------------------------------------------------------
# Giá trị mặc định để chạy được ngay cả khi thiếu file .env. Khi đổi cổng hay
# mật khẩu thì sửa trong .env, không sửa ở đây.
DB_HOST = "127.0.0.1"
DB_PORT = 5434
DB_NAME = "fakereview"
DB_USER = "postgres"
DB_PASSWORD = "postgres"

# Chờ tối đa mỗi lần kết nối (giây).
DB_CONNECT_TIMEOUT_SECONDS = 10

# Container vừa bật có thể mất vài giây mới nhận kết nối, nên thử lại nhiều lần.
DB_CONNECT_ATTEMPTS = 15
DB_CONNECT_DELAY_SECONDS = 1.0

# Thời gian chờ cho một lần kiểm tra trạng thái (đèn báo trên web). Tách khỏi
# DB_CONNECT_TIMEOUT_SECONDS vì đèn báo được gọi lặp lại mỗi 10 giây, không
# được treo lâu như lúc nạp dữ liệu.
DB_HEALTH_TIMEOUT_SECONDS = 2

# Tên container Docker chứa PostgreSQL. Script sao lưu/phục hồi gọi pg_dump và
# pg_restore bên trong container nên phải biết đúng tên này.
DB_CONTAINER_NAME = "fakereview_db"

# Ghi chú: BACKUP_DIR đã khai báo ở khối "Thư mục gốc của từng nhóm" phía trên
# (trỏ tới SaoLuu/). Không khai báo lại để tránh hai nguồn sự thật.

# Tên database tạm dùng khi kiểm tra phục hồi. Phục hồi thử vào database chính
# có thể ghi đè dữ liệu thật, nên dùng database riêng rồi xoá.
DB_RESTORE_SCRATCH_NAME = "fakereview_restore_check"

# --- Chia dữ liệu ------------------------------------------------------------
RANDOM_SEED = 42

# Ba tỉ lệ phải cộng lại bằng 1.0.
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15

# --- Nhãn --------------------------------------------------------------------
# Cột gốc trong CSV.
TEXT_COLUMN = "text_"
LABEL_COLUMN = "label"

# Cột nhãn số 0/1 do MaNguon/data.py tạo ra, dùng cho mọi bước huấn luyện/đánh giá.
LABEL_BINARY_COLUMN = "label_binary"

# Model chỉ nhận số nên phải đổi nhãn chuỗi: review thật (OR) -> 0, review giả
# (CG) -> 1.
LABEL_MAP = {"OR": 0, "CG": 1}

# --- TF-IDF ------------------------------------------------------------------
TFIDF_PARAMS = {
    "ngram_range": (1, 2),
    "min_df": 2,
    "max_features": 50_000,
    "sublinear_tf": True,
    "lowercase": True,
    "strip_accents": "unicode",
}

# --- Mô hình -----------------------------------------------------------------
# loss="log_loss" biến SGD thành hồi quy logistic.
SGD_CLASSIFIER_PARAMS = {
    "loss": "log_loss",
    "alpha": 1e-4,
    "max_iter": 1000,
    "tol": 1e-3,
    "random_state": RANDOM_SEED,
}

# --- Chọn ngưỡng -------------------------------------------------------------
# Quét ngưỡng quyết định để chọn theo F1 cao nhất trên tập val.
THRESHOLD_MIN = 0.05
THRESHOLD_MAX = 0.95
THRESHOLD_STEP = 0.01

# --- Trình bày web -----------------------------------------------------------
# Số khoảng chia trục xác suất (0.0 -> 1.0) khi vẽ biểu đồ phân bố.
HISTOGRAM_BIN_COUNT = 20

# Số dòng mỗi trang của bảng review.
SAMPLE_PAGE_SIZE = 25

# --- Phân nhóm hiển thị -------------------------------------------------------
# Dataset gốc chỉ có nhãn máy sinh (CG) / người viết (OR), không có nhãn bot,
# boost hay spam. Năm mã dưới đây là luật suy luận để hiển thị, không phải nhãn
# ground truth và cũng không phải thuật toán thứ hai.
CATEGORY_GENUINE = "genuine"                  # người viết, đủ dài, không trùng
CATEGORY_FAKE = "suspected_fake"              # model cho là máy sinh
CATEGORY_BOT_BOOST = "suspected_bot_boost"    # máy sinh + 5 sao + quá ngắn
CATEGORY_LOW_CONTENT = "low_content"          # quá ít từ để đánh giá
CATEGORY_DUPLICATE = "spam_duplicate"         # trùng khít một bài phía trước

# Thứ tự cố định khi hiển thị, để web và API sắp cùng một kiểu.
CATEGORY_ORDER = [
    CATEGORY_GENUINE,
    CATEGORY_FAKE,
    CATEGORY_BOT_BOOST,
    CATEGORY_LOW_CONTENT,
    CATEGORY_DUPLICATE,
]

# Review ít hơn 5 từ gần như không có thông tin sản phẩm cụ thể nên bị coi là
# quá ngắn, không đủ để gọi là hữu ích.
MIN_USEFUL_WORDS = 5

# Máy sinh + 5 sao + không quá 25 từ: đủ dài để khen chung chung nhưng thiếu
# chi tiết trải nghiệm, nên bị nghi bot/boost.
BOT_MAX_WORDS = 25

# --- Tải file CSV lên web -----------------------------------------------------
# Không còn giới hạn dung lượng file (mốc 5 MB đã bỏ theo yêu cầu). Chấp nhận
# được vì server chỉ nghe 127.0.0.1 và số dòng đem phân tích vẫn bị chặn bên
# dưới. Đổi lại, cả file vẫn được đọc vào RAM trước khi cắt dòng, nên không mở
# server ra mạng ngoài khi chưa đặt lại giới hạn kích thước.
#
# Số dòng tối đa được phân tích trong một file tải lên. 1.000 đủ cho review
# thực tế; nút thắt thật sự là bước dịch (đã có hạn riêng), con số này chỉ để
# chặn file khổng lồ làm tốn RAM.
MAX_UPLOAD_ROWS = 1000

# Thời gian tối đa (giây) cho bước dịch cả file. 1.000 dòng × khoảng 0,4
# giây/dòng là gần 400 giây, nên 300 giây là mức cân bằng giữa "dịch được phần
# lớn file" và "không để một file lớn treo server". Hết hạn thì các dòng sau
# vẫn được dự đoán trên nội dung gốc, kèm cảnh báo.
MAX_UPLOAD_TRANSLATE_SECONDS = 300

# --- Xóa review tải lên định kỳ ----------------------------------------------
# Review từ file tải lên chỉ để xem lại, không tham gia huấn luyện. Giữ mãi thì
# bảng reviews phình dần (mỗi 1.000 dòng tầm 0,85 MB). Ba tuần đủ để đối chiếu
# kết quả gần đây mà vẫn giữ database nhẹ.
UPLOAD_RETENTION_DAYS = 21

# Tự dọn ngay lúc khởi động API, sau đó chạy định kỳ trong nền. Máy chạy web vì
# thế không cần đặt lịch riêng. Đặt False khi cần giữ upload để điều tra.
UPLOAD_CLEANUP_ENABLED = True

# Khoảng cách giữa hai lần dọn tự động. Một ngày là đủ vì thời gian giữ là 21
# ngày; chạy liên tục chỉ tốn thêm kết nối DB mà không lợi gì.
UPLOAD_CLEANUP_INTERVAL_HOURS = 24

# --- Minh hoạ from-scratch (Notebook/from_scratch_gd_lr.ipynb) ----------------
# Các hằng số này chỉ phục vụ notebook minh hoạ CLO1/CLO2/CLO3, không tham gia
# huấn luyện model thật.

# Tốc độ học dùng chung cho các ví dụ GD/SGD nhỏ.
FROM_SCRATCH_LEARNING_RATE = 0.1

# Số vòng lặp tối đa của các ví dụ GD/SGD.
FROM_SCRATCH_STEPS = 200

# Seed cố định để kết quả in ra tái lập được.
FROM_SCRATCH_SEED = 42

# Bước sai phân khi kiểm tra gradient bằng trung tâm. Quá lớn thì sai số cắt
# cụt, quá nhỏ thì sai số làm tròn số thực.
GRADIENT_CHECK_EPSILON = 1e-5

# Sai số tương đối tối đa được coi là "gradient đúng". Sai phân trung tâm có
# sai số O(eps^2), thực tế thường dưới 1e-8.
GRADIENT_CHECK_TOLERANCE = 1e-6

# Số mẫu tổng hợp cho bài toán hồi quy và phân loại nhỏ trong notebook.
FROM_SCRATCH_SAMPLE_COUNT = 200

# --- Bảng chọn ngưỡng theo chi phí (MaNguon/threshold_cost_table.py) --------------
# Đây là giả định của đồ án, không phải số liệu kinh doanh thật. Ch3 tr.48 yêu
# cầu chọn ngưỡng theo chi phí bỏ lọt/loại nhầm thay vì mặc định 0,5. Chi phí
# tính theo "một review".
COST_FALSE_POSITIVE = 1   # loại nhầm một review thật -> mất một ý kiến khách hàng
COST_FALSE_NEGATIVE = 5   # bỏ lọt một review giả -> ảnh hưởng quyết định mua

# Ngưỡng mặc định để so sánh trong báo cáo (không dùng để chọn).
THRESHOLD_DEFAULT = 0.5
