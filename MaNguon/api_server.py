r"""
API dự đoán review và phục vụ luôn trang web tĩnh.

Ba việc chính:
    1. Dự đoán một câu nhập tay qua POST /api/predict.
    2. Phân tích file CSV tải lên qua POST /api/analyze-file rồi lưu kết quả
       vào PostgreSQL.
    3. Trả các file trong Web/ và DuLieuDemo/ cho trình duyệt.

Chạy tại http://127.0.0.1:8000.

Dùng http.server của thư viện chuẩn thay vì FastAPI vì máy đang chạy Python
3.14.2 rất mới, FastAPI kéo theo pydantic-core là gói biên dịch nên có thể
chưa cài được. http.server luôn có sẵn, không thêm gói nào vào requirements.

Server phục vụ luôn web vì trang gọi API bằng fetch(): mở bằng file:// thì
fetch bị chặn (CORS), còn cùng địa chỉ http://127.0.0.1:8000 thì không lệch
nguồn gốc. File CSV nhận dưới dạng chuỗi trong JSON thay vì multipart vì
phân tích multipart bằng thư viện chuẩn rất dài và dễ lỗi; demo nội bộ chỉ
cần trình duyệt đọc file rồi gửi JSON.
"""

import csv
import hashlib
import io
import json
import math
import pickle
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
from classify import build_summary, classify_review, normalize_text
from config import (
    API_HOST,
    API_PORT,
    CALIBRATION_EPSILON,
    DEMO_DATA_DIR,
    MAX_INPUT_CHARS,
    MAX_UPLOAD_ROWS,
    MAX_UPLOAD_TRANSLATE_SECONDS,
    MIN_KNOWN_TOKEN_RATIO,
    MODEL_PATH,
    TRANSLATE_ENABLED,
    UPLOAD_CLEANUP_ENABLED,
    UPLOAD_CLEANUP_INTERVAL_HOURS,
    UPLOAD_RETENTION_DAYS,
    WEB_DIR,
)
from translate import text_similarity, translate_to_english, translate_to_language

# Bảng kiểu nội dung tự khai báo thay vì dựa vào mimetypes của hệ điều hành.
# Trên Windows registry hay gán .js = text/plain, và một số cấu hình trình
# duyệt có thể từ chối chạy script sai kiểu. Khai báo tay là chắc chắn nhất.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

# MODEL_BUNDLE: gói gồm vectorizer, classifier, threshold, hệ số hiệu chuẩn.
# Nạp một lần lúc khởi động, dùng lại cho mọi request (chỉ đọc nên an toàn với
# nhiều luồng).
MODEL_BUNDLE = None

# MODEL_RUN_ID: id lần huấn luyện trong DB, dùng để gắn review tải lên.
# None nghĩa là DB không sẵn sàng; API vẫn dự đoán được nhưng không lưu.
MODEL_RUN_ID = None

# CLEANUP_STOP_EVENT: báo thread dọn upload tự động dừng cùng server. Dùng Event
# thay vì sleep thường để Ctrl+C tắt ngay, không phải đợi hết một chu kỳ.
CLEANUP_STOP_EVENT = threading.Event()
CLEANUP_THREAD = None


def load_model():
    """Nạp model đã lưu từ đĩa."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Chưa có model tại {MODEL_PATH}.\n"
            "Hãy chạy trước: python MaNguon/train_baseline.py"
        )

    with open(MODEL_PATH, "rb") as file:
        bundle = pickle.load(file)

    print(f"Đã nạp model      : {MODEL_PATH}")
    print(f"Ngưỡng quyết định : {bundle['threshold']:.2f}")
    return bundle


def apply_calibration(probability, slope, intercept):
    """
    Áp dụng hàm Platt đã học lúc train lên một xác suất thô.

    Công thức: sigmoid(slope * logit(p) + intercept).

    Model đã lưu vẫn là model chưa hiệu chuẩn, SGD trả điểm số thô. Bỏ qua
    bước này thì con số API hiển thị sẽ khác con số dùng để chọn ngưỡng lúc
    train, và nhãn có thể lệch theo.
    """
    clipped = min(max(probability, CALIBRATION_EPSILON), 1.0 - CALIBRATION_EPSILON)
    logit = math.log(clipped / (1.0 - clipped))
    return 1.0 / (1.0 + math.exp(-(slope * logit + intercept)))


def predict_review(bundle, text):
    """
    Dự đoán một review và trả về dict kết quả.

    Ngoài xác suất, hàm còn tính tỷ lệ token có trong từ vựng model. Câu tiếng
    Việt cho ra vector gần như toàn số 0, model vẫn trả một con số trông rất
    "tự tin" nhưng vô nghĩa; tỷ lệ này phát hiện đúng trường hợp đó.
    """
    vectorizer = bundle["vectorizer"]
    classifier = bundle["classifier"]
    threshold = bundle["threshold"]

    # Hệ số hiệu chuẩn; model cũ chưa có thì dùng 1.0 / 0.0 (không đổi gì).
    slope = float(bundle.get("platt_slope", 1.0))
    intercept = float(bundle.get("platt_intercept", 0.0))

    # build_analyzer() trả về đúng hàm tách từ mà TF-IDF đã dùng lúc train
    # (lowercase + bỏ dấu + tách từ + ghép cụm 1-2 từ).
    analyzer = vectorizer.build_analyzer()
    tokens = analyzer(text)
    vocabulary = vectorizer.vocabulary_

    known_token_count = 0
    for token in tokens:
        if token in vocabulary:
            known_token_count = known_token_count + 1

    if len(tokens) == 0:
        known_token_ratio = 0.0
    else:
        known_token_ratio = known_token_count / len(tokens)

    feature_matrix = vectorizer.transform([text])
    probabilities = classifier.predict_proba(feature_matrix)[0]

    # predict_proba xếp cột theo classifier.classes_, nên phải tra đúng vị trí
    # của lớp 1 (giả) thay vì giả định nó luôn nằm ở cột thứ hai.
    positive_index = list(classifier.classes_).index(1)
    probability_raw = float(probabilities[positive_index])

    probability_fake = apply_calibration(probability_raw, slope, intercept)
    predicted_label = 1 if probability_fake >= threshold else 0

    return {
        "probability_fake": round(probability_fake, 4),
        # Giữ thêm số CHƯA làm tròn để so ngưỡng. Nếu so trên số đã làm tròn,
        # một review sát ngưỡng có thể đổi nhãn chỉ vì bước hiển thị.
        "probability_fake_raw": probability_fake,
        "probability_real": round(1.0 - probability_fake, 4),
        "label": predicted_label,
        "label_name": "fake" if predicted_label == 1 else "real",
        "threshold": threshold,
        "known_token_count": known_token_count,
        "token_count": len(tokens),
        "known_token_ratio": round(known_token_ratio, 4),
        "is_reliable": known_token_ratio >= MIN_KNOWN_TOKEN_RATIO,
        "char_count": len(text),
    }


def clean_upload_text(value):
    """Gộp khoảng trắng thừa của một ô CSV; thiếu giá trị -> chuỗi rỗng."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def parse_rating(value):
    """
    Đổi ô rating sang float; thiếu hoặc không phải số -> None.

    Không dùng pandas ở đây vì API chỉ cần một phép đổi nhỏ, không đáng kéo
    cả thư viện dữ liệu lớn vào tiến trình server.
    """
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    # NaN là giá trị không bằng chính nó.
    if number != number:
        return None
    return round(number, 1)


def find_text_column(fieldnames):
    """Chọn cột nội dung: ưu tiên text_ (tên gốc của dataset), sau đó text."""
    for candidate in ("text_", "text"):
        if candidate in fieldnames:
            return candidate
    return None


def content_hash(text):
    """Băm nội dung review sau chuẩn hóa, dùng để tra trùng lặp."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def analyze_csv_text(csv_text, translate_rows):
    """
    Phân tích toàn bộ nội dung CSV và trả về dict cho lớp web.

    Các bước:
      1. Đọc CSV, tìm cột nội dung.
      2. Cắt còn tối đa MAX_UPLOAD_ROWS dòng.
      3. Với mỗi dòng: dịch (nếu bật), dự đoán, xếp nhóm, gắn cờ.
      4. Tổng hợp số lượng theo nhóm và theo số sao.
    """
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    fieldnames = reader.fieldnames or []

    text_column = find_text_column(fieldnames)
    if text_column is None:
        raise ValueError(
            "File CSV phải có cột 'text_' hoặc 'text'. "
            f"Các cột đang có: {fieldnames}"
        )

    all_rows = list(reader)
    total_rows = len(all_rows)

    truncated_rows = 0
    if total_rows > MAX_UPLOAD_ROWS:
        truncated_rows = total_rows - MAX_UPLOAD_ROWS
        all_rows = all_rows[:MAX_UPLOAD_ROWS]

    start_time = time.monotonic()
    deadline = start_time + MAX_UPLOAD_TRANSLATE_SECONDS

    rows = []
    seen_texts = set()
    skipped_rows = 0
    translation_cutoff = False

    for raw_row in all_rows:
        text = clean_upload_text(raw_row.get(text_column))
        if text == "":
            skipped_rows = skipped_rows + 1
            continue

        rating = None
        if "rating" in fieldnames:
            rating = parse_rating(raw_row.get("rating"))

        product_category = ""
        if "category" in fieldnames:
            product_category = clean_upload_text(raw_row.get("category"))

        translated_text = text
        used_translation = False
        translation_error = ""
        translation_provider = ""
        detected_language = ""

        if translate_rows and TRANSLATE_ENABLED:
            if time.monotonic() >= deadline:
                # Hết thời gian dịch: các dòng sau dùng nguyên bản. Không dừng
                # cả file, vì người dùng vẫn cần kết quả phân loại.
                translation_cutoff = True
            else:
                translation = translate_to_english(text)
                translated_text = translation["translated_text"]
                used_translation = translation["used_translation"]
                translation_error = translation["error"]
                translation_provider = translation["provider"]
                detected_language = translation["detected_language"]

                # Câu tiếng Anh thường được dịch trả lại y nguyên. Khi đó không
                # đánh dấu "đã dịch", tránh hiện nhãn thừa trên giao diện.
                if used_translation and normalize_text(translated_text) == normalize_text(text):
                    used_translation = False

        prediction = predict_review(MODEL_BUNDLE, translated_text)

        # Trùng lặp xét trên nội dung GỐC: dịch máy có thể biến hai câu khác
        # nhau thành cùng một câu, làm báo trùng sai.
        normalized = normalize_text(text)
        is_duplicate = False
        if normalized != "":
            is_duplicate = normalized in seen_texts
            seen_texts.add(normalized)

        classification = classify_review(
            text=text,
            probability_fake=prediction["probability_fake_raw"],
            threshold=prediction["threshold"],
            rating=rating,
            is_duplicate=is_duplicate,
            known_token_ratio=prediction["known_token_ratio"],
            used_translation=used_translation,
        )

        rows.append(
            {
                "row_index": len(rows),
                "text": text,
                "translated_text": translated_text,
                "used_translation": used_translation,
                "translation_error": translation_error,
                "translation_provider": translation_provider,
                "detected_language": detected_language,
                "rating": rating,
                "product_category": product_category,
                "true_label": None,
                "is_correct": None,
                "prob_fake": prediction["probability_fake"],
                "predicted_label": prediction["label"],
                "category": classification["primary_category"],
                "category_basis": classification["category_basis"],
                "flag_source": classification["flag_source"],
                "flags": classification["flags"],
                "reasons": classification["reasons"],
                "is_reliable": classification["is_reliable"],
                "is_useful": classification["is_useful"],
                "word_count": classification["word_count"],
                "known_token_ratio": classification["known_token_ratio"],
                "translation_borderline": classification["translation_borderline"],
                "translation_inconsistent": classification["translation_inconsistent"],
            }
        )

    summary = build_summary(rows)
    elapsed_seconds = round(time.monotonic() - start_time, 1)

    warnings = []
    if skipped_rows > 0:
        warnings.append(f"Đã bỏ qua {skipped_rows} dòng không có nội dung.")
    if truncated_rows > 0:
        warnings.append(
            f"File có {total_rows} dòng, chỉ phân tích {MAX_UPLOAD_ROWS} dòng đầu "
            f"(bỏ qua {truncated_rows} dòng)."
        )
    if "rating" not in fieldnames:
        warnings.append(
            "File không có cột 'rating' nên bảng 5 sao không có dữ liệu."
        )
    if translate_rows and translation_cutoff:
        warnings.append(
            "Đã hết thời gian dịch "
            f"{MAX_UPLOAD_TRANSLATE_SECONDS} giây; các dòng sau được dự đoán "
            "trên nội dung gốc."
        )

    return {
        "rows": rows,
        "summary": summary,
        "warnings": warnings,
        "meta": {
            "total_rows": total_rows,
            "analyzed_rows": len(rows),
            "skipped_rows": skipped_rows,
            "truncated_rows": truncated_rows,
            "translate_requested": bool(translate_rows),
            "translation_cutoff": translation_cutoff,
            "elapsed_seconds": elapsed_seconds,
            "threshold": MODEL_BUNDLE["threshold"],
        },
    }


def save_analysis_to_database(file_name, analysis):
    """
    Lưu một lần phân tích file vào PostgreSQL.

    Trả về (batch_id, cảnh báo). batch_id = None nghĩa là không lưu được.
    Hàm không ném lỗi vì người dùng vẫn cần kết quả phân tích trên màn hình
    dù database tạm thời không kết nối được.
    """
    if MODEL_RUN_ID is None:
        return None, "Không lưu được vào PostgreSQL (database chưa sẵn sàng)."

    try:
        connection = db.connect()
        try:
            meta = analysis["meta"]
            batch_id = db.insert_upload_batch(
                connection=connection,
                file_name=file_name,
                rows_total=meta["total_rows"],
                rows_analyzed=meta["analyzed_rows"],
                translate_requested=meta["translate_requested"],
                elapsed_seconds=meta["elapsed_seconds"],
                summary=analysis["summary"],
                warnings=analysis["warnings"],
            )

            # Chỉ chèn các cột bảng reviews cần; vài khóa chỉ dùng cho giao diện
            # (translation_error, is_correct) nên không đưa vào DB.
            db_reviews = []
            for row in analysis["rows"]:
                db_reviews.append(
                    {
                        "row_index": row["row_index"],
                        "text": row["text"],
                        "translated_text": row["translated_text"],
                        "used_translation": row["used_translation"],
                        "rating": row["rating"],
                        "product_category": row["product_category"],
                        "true_label": None,
                        "prob_fake": row["prob_fake"],
                        "predicted_label": row["predicted_label"],
                        "category": row["category"],
                        "flags": row["flags"],
                        "reasons": row["reasons"],
                        "is_useful": row["is_useful"],
                        "is_reliable": row["is_reliable"],
                        "word_count": row["word_count"],
                        "known_token_ratio": row["known_token_ratio"],
                        "content_hash": content_hash(row["text"]),
                    }
                )

            db.insert_upload_reviews(connection, MODEL_RUN_ID, batch_id, db_reviews)
            return batch_id, ""
        finally:
            connection.close()
    except Exception as error:
        return None, f"Không lưu được kết quả vào PostgreSQL: {error}"


class RequestHandler(BaseHTTPRequestHandler):
    """Xử lý GET file tĩnh và POST hai endpoint API."""

    def do_GET(self):
        if self.path.split("?")[0] == "/api/health":
            self.handle_health()
            return
        self.serve_static_file()

    def do_POST(self):
        if self.path == "/api/predict":
            self.handle_predict()
        elif self.path == "/api/analyze-file":
            self.handle_analyze_file()
        else:
            self.send_json(404, {"error": "Không có endpoint này"})

    def handle_health(self):
        """
        GET /api/health - trả trạng thái PostgreSQL cho đèn báo trên giao diện.

        Luôn trả HTTP 200 vì giao diện chỉ cần đọc JSON. Nếu trả 503 khi DB
        tắt thì fetch() vẫn đọc được body, nhưng vài đoạn mã coi mã lỗi là
        "không gọi được API" nên sẽ hiển thị sai trạng thái.

        Chỉ kiểm tra một lần vì endpoint này được gọi lặp lại mỗi 10 giây;
        dùng connect() có thử lại 15 lần sẽ làm treo mỗi lần DB tắt.
        """
        health = db.check_health()

        payload = {
            "database": health["connected"],
            "latency_ms": health["latency_ms"],
            "checked_at": datetime.now(timezone.utc).astimezone().isoformat(
                timespec="seconds"
            ),
            "message": (
                "Đã kết nối PostgreSQL"
                if health["connected"]
                else "Không kết nối được PostgreSQL"
            ),
        }

        # Chi tiết lỗi chỉ in ở console server: có thể chứa host/user, không cần
        # thiết cho giao diện và không nên gửi ra ngoài.
        if not health["connected"]:
            print(f"[DB] Kiểm tra trạng thái thất bại: {health['error']}")

        self.send_json(200, payload)

    def serve_static_file(self):
        requested_path = self.path.split("?")[0]
        if requested_path == "/":
            requested_path = "/index.html"

        relative_path = requested_path.lstrip("/")

        # Hai thư mục tĩnh: Web/ cho giao diện, DuLieuDemo/ cho dữ liệu sinh ra.
        # HTML nằm ở Web/ nhưng nạp dữ liệu bằng ../DuLieuDemo/data_meta.js.
        # Chạy qua HTTP, trình duyệt chuẩn hoá "../" thành /DuLieuDemo/... nên
        # server phải tách nhánh và phục vụ đúng thư mục đó.
        if relative_path == "DuLieuDemo" or relative_path.startswith("DuLieuDemo/"):
            base_dir = DEMO_DATA_DIR
            relative_path = relative_path[len("DuLieuDemo"):].lstrip("/")
        else:
            base_dir = WEB_DIR

        file_path = (base_dir / relative_path).resolve()

        # Chặn truy cập ra ngoài thư mục được phục vụ (ví dụ ../../config.py).
        if not file_path.is_relative_to(base_dir.resolve()):
            self.send_json(403, {"error": "Đường dẫn không hợp lệ"})
            return

        if not file_path.is_file():
            self.send_json(404, {"error": f"Không tìm thấy {requested_path}"})
            return

        content_type = CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
        file_bytes = file_path.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(file_bytes)))
        self.end_headers()
        self.wfile.write(file_bytes)

    def read_json_body(self):
        """
        Đọc body JSON, trả về (dict, thông báo lỗi).

        Tách hàm vì hai endpoint cùng cần đọc và kiểm tra JSON; viết một lần
        để quy tắc đọc không bị lệch giữa hai nơi.

        Không chặn theo kích thước body vì mốc 5 MB đã bỏ theo yêu cầu. Số
        dòng đem phân tích vẫn bị cắt bởi MAX_UPLOAD_ROWS, còn endpoint nhập
        tay vẫn chặn độ dài câu bằng MAX_INPUT_CHARS.
        """
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return None, "Thiếu nội dung gửi lên"

        raw_body = self.rfile.read(content_length)

        try:
            request_body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "Dữ liệu gửi lên không phải JSON hợp lệ"

        if not isinstance(request_body, dict):
            return None, "Body phải là object JSON"

        return request_body, ""

    def handle_predict(self):
        request_body, error_message = self.read_json_body()
        if error_message:
            self.send_json(400, {"error": error_message})
            return

        text = str(request_body.get("text", "")).strip()

        if not text:
            self.send_json(400, {"error": "Review rỗng, hãy nhập nội dung"})
            return

        if len(text) > MAX_INPUT_CHARS:
            self.send_json(
                400, {"error": f"Review dài quá {MAX_INPUT_CHARS} ký tự"}
            )
            return

        original_text = text
        translated_text = text
        used_translation = False
        translation_error = ""
        translation_provider = ""
        detected_language = ""
        translation_similarity = None

        # Dịch sang tiếng Anh trước khi dự đoán, vì model chỉ học từ vựng
        # tiếng Anh. Nếu dịch lỗi, translate_to_english trả lại câu gốc kèm
        # thông báo lỗi; khi đó tỷ lệ token quen thuộc sẽ thấp và web cảnh báo.
        if TRANSLATE_ENABLED:
            translation = translate_to_english(text)
            translated_text = translation["translated_text"]
            used_translation = translation["used_translation"]
            translation_error = translation["error"]
            translation_provider = translation["provider"]
            detected_language = translation["detected_language"]

            # Câu tiếng Anh thường được dịch trả lại y nguyên. Khi đó không
            # đánh dấu "đã dịch", tránh hiện nhãn thừa trên giao diện.
            if used_translation and normalize_text(translated_text) == normalize_text(text):
                used_translation = False

            # Dịch vòng chỉ chạy cho câu NHẬP TAY, không chạy cho cả file CSV:
            # mỗi dòng sẽ tốn thêm một request, làm file lớn chậm gấp đôi.
            # Nếu dịch vòng lỗi mạng, bỏ qua kiểm tra thay vì kết luận sai.
            if used_translation and detected_language not in ("", "en"):
                back_translation = translate_to_language(
                    translated_text, detected_language
                )
                if back_translation["used_translation"] and back_translation["error"] == "":
                    translation_similarity = text_similarity(
                        original_text, back_translation["translated_text"]
                    )

        try:
            result = predict_review(MODEL_BUNDLE, translated_text)
        except Exception as error:
            # Không để server chết vì một request lỗi: báo lỗi rồi tiếp tục.
            self.send_json(500, {"error": f"Lỗi khi dự đoán: {error}"})
            return

        # Nhập tay không có số sao, nên is_five_star luôn sai và nhóm
        # bot/boost không xuất hiện ở đây. Đó là hành vi có chủ ý, không phải lỗi.
        classification = classify_review(
            text=original_text,
            probability_fake=result["probability_fake_raw"],
            threshold=result["threshold"],
            rating=None,
            is_duplicate=False,
            known_token_ratio=result["known_token_ratio"],
            used_translation=used_translation,
            translation_similarity=translation_similarity,
        )

        # Gửi kèm bản dịch để lớp web hiện đúng câu model đã đọc. Người dùng
        # phải tự kiểm chứng được bước dịch, không phải tin vào một con số
        # không rõ nguồn gốc.
        result["original_text"] = original_text
        result["translated_text"] = translated_text
        result["used_translation"] = used_translation
        result["translation_error"] = translation_error
        result["translation_provider"] = translation_provider
        result["detected_language"] = detected_language
        result["translation_similarity"] = (
            None if translation_similarity is None else round(translation_similarity, 4)
        )
        result["category"] = classification["primary_category"]
        result["category_basis"] = classification["category_basis"]
        result["flag_source"] = classification["flag_source"]
        result["flags"] = classification["flags"]
        result["reasons"] = classification["reasons"]
        result["is_useful"] = classification["is_useful"]
        result["word_count"] = classification["word_count"]
        result["translation_borderline"] = classification["translation_borderline"]
        result["translation_inconsistent"] = classification["translation_inconsistent"]

        self.send_json(200, result)

    def handle_analyze_file(self):
        request_body, error_message = self.read_json_body()
        if error_message:
            self.send_json(400, {"error": error_message})
            return

        csv_text = str(request_body.get("csv_text", ""))
        if csv_text.strip() == "":
            self.send_json(400, {"error": "File CSV rỗng"})
            return

        translate_rows = bool(request_body.get("translate", True))
        file_name = str(request_body.get("file_name", "uploaded.csv")).strip()
        if file_name == "":
            file_name = "uploaded.csv"

        try:
            analysis = analyze_csv_text(csv_text, translate_rows)
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return
        except Exception as error:
            # Không để server chết vì một file lỗi.
            self.send_json(500, {"error": f"Lỗi khi phân tích file: {error}"})
            return

        batch_id, database_warning = save_analysis_to_database(file_name, analysis)
        analysis["meta"]["batch_id"] = batch_id
        if database_warning:
            analysis["warnings"].append(database_warning)

        self.send_json(200, analysis)

    def send_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def cleanup_old_uploads(connection=None):
    """
    Xóa review upload cũ, báo kết quả ra console nhưng không ném lỗi ra ngoài.

    Hàm này chạy cả khi khởi động lẫn trong thread nền, nên lỗi DB chỉ được in
    ra; API vẫn tiếp tục dự đoán và tải file bình thường. Truyền connection có
    sẵn để khỏi mở kết nối mới lúc khởi động.
    """
    own_connection = connection is None
    if own_connection:
        try:
            connection = db.connect()
        except Exception as error:
            print(f"[DB] Dọn tự động: không kết nối được: {error}")
            return None

    try:
        removed = db.delete_old_uploads(connection, UPLOAD_RETENTION_DAYS)
        total = (
            removed["batches"]
            + removed["reviews"]
            + removed["orphan_reviews"]
        )
        if total:
            print(
                f"[DB] Đã xóa {removed['batches']} lô upload cũ "
                f"({removed['reviews']} review, "
                f"{removed['orphan_reviews']} review mồ côi)."
            )
        return removed
    except Exception as error:
        # pg8000 giữ transaction ở trạng thái lỗi sau một câu lệnh hỏng; phải
        # rollback thì các truy vấn sau mới chạy tiếp.
        connection.rollback()
        print(f"[DB] Không dọn được upload cũ: {error}")
        return None
    finally:
        if own_connection:
            connection.close()


def cleanup_loop():
    """Chạy dọn upload cũ định kỳ trong nền, không cần Task Scheduler."""
    wait_seconds = UPLOAD_CLEANUP_INTERVAL_HOURS * 3600
    while not CLEANUP_STOP_EVENT.wait(wait_seconds):
        cleanup_old_uploads()


def prepare_database():
    """
    Chuẩn bị DB cho API và trả về model_run_id mới nhất.

    Không dừng server khi DB lỗi vì người dùng vẫn cần dự đoán nhập tay. Chỉ
    phần lưu trữ bị tắt, và mỗi lần tải file sẽ kèm cảnh báo rõ ràng.
    """
    try:
        connection = db.connect()
        try:
            db.init_schema(connection)
            if UPLOAD_CLEANUP_ENABLED:
                cleanup_old_uploads(connection)
            model_run = db.get_latest_model_run(connection)
            if model_run is None:
                print("[DB] Bảng model_runs trống. Hãy chạy: python MaNguon\\load_db.py")
                return None
            print(f"[DB] Dùng lần chạy model id={model_run['id']}")
            return model_run["id"]
        finally:
            connection.close()
    except Exception as error:
        print(f"[DB] Không kết nối được PostgreSQL: {error}")
        print("[DB] API vẫn chạy nhưng sẽ KHÔNG lưu kết quả tải file.")
        return None


def main():
    global MODEL_BUNDLE, MODEL_RUN_ID, CLEANUP_THREAD
    MODEL_BUNDLE = load_model()
    MODEL_RUN_ID = prepare_database()

    if UPLOAD_CLEANUP_ENABLED:
        CLEANUP_THREAD = threading.Thread(
            target=cleanup_loop, name="upload-cleanup", daemon=True
        )
        CLEANUP_THREAD.start()

    server = ThreadingHTTPServer((API_HOST, API_PORT), RequestHandler)

    print("")
    print(f"Web + API đang chạy tại http://{API_HOST}:{API_PORT}/")
    print("Mở đúng địa chỉ trên (KHÔNG double-click index.html) để ô nhập hoạt động.")
    if UPLOAD_CLEANUP_ENABLED:
        print(
            f"Tự dọn review upload cũ mỗi {UPLOAD_CLEANUP_INTERVAL_HOURS} giờ "
            f"(giữ {UPLOAD_RETENTION_DAYS} ngày)."
        )
    print("Nhấn Ctrl+C để dừng.")
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng server.")
    finally:
        CLEANUP_STOP_EVENT.set()
        if CLEANUP_THREAD is not None:
            CLEANUP_THREAD.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    main()
