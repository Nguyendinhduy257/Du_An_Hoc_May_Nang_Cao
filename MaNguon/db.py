r"""
Nơi duy nhất chứa mã truy cập PostgreSQL của dự án.

load_db, export_web_data, api_server... đều đi qua đây, không tự mở kết nối
riêng. Thông tin kết nối lấy từ ThuMucChienKhai\.env, cấu trúc bảng ở
ThuMucChienKhai\db\schema.sql.

Dùng pg8000 vì đây là thư viện Python thuần: máy chạy Python 3.14.2 rất mới,
psycopg2 cần thư viện biên dịch nên dễ không có bản cài tương thích.
"""

import json
import time

import pg8000.dbapi

from config import (
    DB_CONNECT_ATTEMPTS,
    DB_CONNECT_DELAY_SECONDS,
    DB_CONNECT_TIMEOUT_SECONDS,
    DB_HEALTH_TIMEOUT_SECONDS,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    DEPLOY_DIR,
)

# ENV_PATH: file cấu hình thật trên máy, KHÔNG đưa lên mạng.
# Nằm trong ThuMucChienKhai vì docker compose đọc .env cùng thư mục với
# docker-compose.yml, đặt cạnh nhau thì khỏi phải chỉ định --env-file.
ENV_PATH = DEPLOY_DIR / ".env"

# SCHEMA_PATH: file SQL tạo bảng, dùng chung với Docker
# (docker-compose.yml mount ./db/schema.sql tính từ ThuMucChienKhai/).
SCHEMA_PATH = DEPLOY_DIR / "db" / "schema.sql"


def read_env_file(path):
    """
    Đọc file .env dạng KEY=VALUE thành dict.

    Tự viết thay vì dùng python-dotenv để khỏi thêm thư viện chỉ nhằm đọc vài
    dòng cấu hình; định dạng .env ở đây rất đơn giản.
    """
    values = {}

    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        # Bỏ dòng trống và dòng chú thích.
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        # split("=", 1): giá trị có thể chứa dấu "=", chỉ tách ở dấu đầu tiên.
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def get_settings():
    """
    Gộp giá trị mặc định trong config.py với giá trị ghi đè trong .env.

    Ưu tiên .env để người dùng chỉ sửa một chỗ khi đổi cổng hoặc mật khẩu;
    config.py vẫn có mặc định để chạy được khi thiếu .env.
    """
    env_values = read_env_file(ENV_PATH)

    return {
        "host": env_values.get("POSTGRES_HOST", DB_HOST),
        "port": int(env_values.get("POSTGRES_PORT", DB_PORT)),
        "database": env_values.get("POSTGRES_DB", DB_NAME),
        "user": env_values.get("POSTGRES_USER", DB_USER),
        "password": env_values.get("POSTGRES_PASSWORD", DB_PASSWORD),
    }


def connect():
    """
    Mở kết nối tới PostgreSQL, có thử lại.

    Thử lại vì container Docker vừa bật có thể mất vài giây mới nhận kết nối.
    Nếu chỉ thử một lần, script sẽ báo lỗi oan ngay sau docker compose up.
    """
    settings = get_settings()
    last_error = None

    for attempt in range(1, DB_CONNECT_ATTEMPTS + 1):
        try:
            return pg8000.dbapi.connect(
                user=settings["user"],
                password=settings["password"],
                host=settings["host"],
                port=settings["port"],
                database=settings["database"],
                timeout=DB_CONNECT_TIMEOUT_SECONDS,
            )
        except Exception as error:  # pg8000 ném nhiều loại lỗi khác nhau
            last_error = error
            print(
                f"[DB] Kết nối thất bại lần {attempt}/{DB_CONNECT_ATTEMPTS}: {error}"
            )
            time.sleep(DB_CONNECT_DELAY_SECONDS)

    raise RuntimeError(f"Không kết nối được PostgreSQL: {last_error}")


def split_sql_statements(sql_text):
    """
    Tách file .sql thành từng câu lệnh.

    pg8000 chỉ chạy được một câu lệnh mỗi lần execute, nên phải bỏ dòng chú
    thích (bắt đầu bằng --) rồi cắt theo dấu ";". Schema của dự án không có
    function/trigger nên không chứa ";" bên trong.
    """
    lines_without_comments = []

    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines_without_comments.append(line)

    cleaned = "\n".join(lines_without_comments)

    statements = []
    for piece in cleaned.split(";"):
        statement = piece.strip()
        if statement:
            statements.append(statement)

    return statements


def init_schema(connection):
    """
    Tạo bảng nếu chưa có.

    Cần bước này dù Docker đã chạy schema.sql, vì script đó chỉ chạy ở lần
    khởi tạo volume đầu tiên. Volume đã tồn tại từ trước thì schema có thể
    thiếu bảng.
    """
    sql_text = SCHEMA_PATH.read_text(encoding="utf-8")

    cursor = connection.cursor()
    try:
        for statement in split_sql_statements(sql_text):
            cursor.execute(statement)
        connection.commit()
    finally:
        cursor.close()


def to_json_text(value):
    """
    Đổi list/dict Python thành chuỗi JSON để ghi vào cột JSONB.

    ensure_ascii=False: giữ nguyên tiếng Việt có dấu trong DB, dễ đọc khi tra cứu.
    """
    return json.dumps(value, ensure_ascii=False)


def save_model_run(connection, model_name, threshold, metrics, config_values):
    """
    Lưu một lần huấn luyện và trả về id vừa tạo.

    Lưu cả metrics và config để sau này xem lại một kết quả cũ còn biết nó
    sinh ra từ tham số nào, không chỉ thấy con số cuối cùng.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO model_runs (model_name, threshold, metrics, config)
            VALUES (%s, %s, %s::jsonb, %s::jsonb)
            RETURNING id
            """,
            (
                model_name,
                threshold,
                to_json_text(metrics),
                to_json_text(config_values),
            ),
        )
        model_run_id = int(cursor.fetchone()[0])
        connection.commit()
        return model_run_id
    finally:
        cursor.close()


def get_latest_model_run(connection):
    """
    Lấy lần huấn luyện mới nhất.

    Trả dict hoặc None nếu bảng còn trống. Dùng ORDER BY id DESC thay vì
    created_at vì id tăng đơn điệu, không phụ thuộc đồng hồ máy.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT id, model_name, threshold, metrics, config, created_at
            FROM model_runs
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row is None:
            return None

        return {
            "id": int(row[0]),
            "model_name": row[1],
            "threshold": float(row[2]),
            "metrics": row[3],
            "config": row[4],
            "created_at": row[5],
        }
    finally:
        cursor.close()


# Câu lệnh chèn review dùng chung cho cả dữ liệu demo và dữ liệu tải lên.
# Để ở mức module cho có một nơi duy nhất, tránh hai hàm chèn lệch cột nhau.
INSERT_REVIEW_SQL = """
    INSERT INTO reviews (
        model_run_id, batch_id, dataset_split, row_index,
        text, translated_text, used_translation,
        rating, product_category, true_label,
        prob_fake, predicted_label, category,
        flags, reasons, is_useful, is_reliable,
        word_count, known_token_ratio, content_hash
    ) VALUES (
        %s, %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s::jsonb, %s::jsonb, %s, %s,
        %s, %s, %s
    )
"""


def build_review_values(model_run_id, batch_id, dataset_split, review):
    """
    Chuyển một dict review thành bộ giá trị đúng thứ tự cột của INSERT_REVIEW_SQL.

    Tách hàm riêng vì load_db và api_server dùng cùng một cách đóng gói; sau
    này thêm cột chỉ phải sửa một chỗ.
    """
    return (
        model_run_id,
        batch_id,
        dataset_split,
        int(review["row_index"]),
        review["text"],
        review.get("translated_text", ""),
        bool(review.get("used_translation", False)),
        review.get("rating"),
        review.get("product_category", ""),
        review.get("true_label"),
        float(review["prob_fake"]),
        int(review["predicted_label"]),
        review["category"],
        to_json_text(review.get("flags", [])),
        to_json_text(review.get("reasons", [])),
        bool(review["is_useful"]),
        bool(review["is_reliable"]),
        int(review["word_count"]),
        float(review.get("known_token_ratio", 1.0)),
        review["content_hash"],
    )


def replace_split_reviews(connection, model_run_id, dataset_split, reviews):
    """
    Nạp lại toàn bộ một tập demo (test hoặc val) cho một lần chạy model.

    Xóa trước rồi chèn để script chạy lại được nhiều lần mà không nhân đôi dữ
    liệu. Xóa theo đúng (model_run_id, dataset_split) nên không đụng tới dữ
    liệu của lần chạy khác hay dữ liệu người dùng tải lên.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            DELETE FROM reviews
            WHERE model_run_id = %s AND dataset_split = %s AND batch_id IS NULL
            """,
            (model_run_id, dataset_split),
        )

        values = [
            build_review_values(model_run_id, None, dataset_split, review)
            for review in reviews
        ]
        if values:
            cursor.executemany(INSERT_REVIEW_SQL, values)

        connection.commit()
    finally:
        cursor.close()


def insert_upload_batch(
    connection, file_name, rows_total, rows_analyzed, translate_requested,
    elapsed_seconds, summary, warnings
):
    """Lưu thông tin một lần tải file CSV và trả về id lô."""
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO upload_batches (
                file_name, rows_total, rows_analyzed, translate_requested,
                elapsed_seconds, summary, warnings
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            RETURNING id
            """,
            (
                file_name,
                int(rows_total),
                int(rows_analyzed),
                bool(translate_requested),
                float(elapsed_seconds),
                to_json_text(summary),
                to_json_text(warnings),
            ),
        )
        batch_id = int(cursor.fetchone()[0])
        connection.commit()
        return batch_id
    finally:
        cursor.close()


def insert_upload_reviews(connection, model_run_id, batch_id, reviews):
    """Chèn toàn bộ review của một file tải lên."""
    cursor = connection.cursor()
    try:
        values = [
            build_review_values(model_run_id, batch_id, "upload", review)
            for review in reviews
        ]
        if values:
            cursor.executemany(INSERT_REVIEW_SQL, values)
        connection.commit()
    finally:
        cursor.close()


def delete_old_uploads(connection, retention_days, dry_run=False):
    """
    Xóa review tải lên đã cũ để database không phình theo thời gian.

    Chỉ đụng dữ liệu dataset_split='upload'. Dữ liệu demo test/val có batch_id
    NULL và nằm ngoài phạm vi này nên luôn được giữ lại. Xóa một dòng trong
    upload_batches là đủ để review của lô đó biến mất nhờ khóa ngoại
    ON DELETE CASCADE; riêng dòng upload mồ côi (batch_id NULL) phải xóa thêm.

    dry_run=True chỉ đếm, không xóa, để dò ngưỡng trước khi chạy thật.

    Trả về dict gồm retention_days, cutoff, batches, reviews, orphan_reviews;
    số liệu là số sẽ bị xóa (bằng số đã xóa khi chạy thật).
    """
    cursor = connection.cursor()
    try:
        # Lấy mốc thời gian từ chính PostgreSQL để không lệch nếu đồng hồ
        # Python và container khác nhau.
        cursor.execute(
            "SELECT now() - make_interval(days => %s::int)",
            (int(retention_days),),
        )
        cutoff = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM upload_batches WHERE created_at < %s),
                (SELECT count(*) FROM reviews
                 WHERE dataset_split = 'upload'
                   AND batch_id IN (
                       SELECT id FROM upload_batches WHERE created_at < %s
                   )),
                (SELECT count(*) FROM reviews
                 WHERE dataset_split = 'upload'
                   AND batch_id IS NULL AND created_at < %s)
            """,
            (cutoff, cutoff, cutoff),
        )
        batches, reviews, orphan_reviews = [int(value) for value in cursor.fetchone()]

        if not dry_run and (batches or orphan_reviews):
            cursor.execute(
                "DELETE FROM upload_batches WHERE created_at < %s",
                (cutoff,),
            )
            cursor.execute(
                """
                DELETE FROM reviews
                WHERE dataset_split = 'upload'
                  AND batch_id IS NULL AND created_at < %s
                """,
                (cutoff,),
            )
            connection.commit()

        return {
            "retention_days": int(retention_days),
            "cutoff": cutoff,
            "batches": batches,
            "reviews": reviews,
            "orphan_reviews": orphan_reviews,
        }
    finally:
        cursor.close()


def row_to_dict(cursor, row):
    """Ghép một dòng kết quả với tên cột để trả về dict."""
    column_names = [description[0] for description in cursor.description]
    return dict(zip(column_names, row))


def fetch_split_reviews(connection, dataset_split, model_run_id):
    """
    Đọc toàn bộ review demo của một tập, sắp theo row_index.

    Sắp theo row_index để bảng trên web giữ đúng thứ tự như file CSV gốc,
    không thì người xem không đối chiếu được với dữ liệu nguồn.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT row_index, text, translated_text, used_translation,
                   rating, product_category, true_label,
                   prob_fake, predicted_label, category,
                   flags, reasons, is_useful, is_reliable, word_count,
                   known_token_ratio, content_hash
            FROM reviews
            WHERE dataset_split = %s AND model_run_id = %s AND batch_id IS NULL
            ORDER BY row_index
            """,
            (dataset_split, model_run_id),
        )
        rows = cursor.fetchall()

        result = []
        for row in rows:
            item = row_to_dict(cursor, row)

            # pg8000 trả NUMERIC dạng Decimal; đổi sang float để JSON và phép
            # so sánh ngưỡng phía sau hoạt động như số thực bình thường.
            item["prob_fake"] = float(item["prob_fake"])
            item["known_token_ratio"] = float(item["known_token_ratio"])
            if item["rating"] is not None:
                item["rating"] = float(item["rating"])

            result.append(item)

        return result
    finally:
        cursor.close()


def fetch_upload_reviews(connection, batch_id):
    """Đọc lại review của một lô tải lên (dùng khi cần tra cứu lại)."""
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT row_index, text, translated_text, used_translation,
                   rating, product_category, true_label,
                   prob_fake, predicted_label, category,
                   flags, reasons, is_useful, is_reliable, word_count,
                   known_token_ratio, content_hash
            FROM reviews
            WHERE batch_id = %s
            ORDER BY row_index
            """,
            (batch_id,),
        )
        rows = cursor.fetchall()

        result = []
        for row in rows:
            item = row_to_dict(cursor, row)
            item["prob_fake"] = float(item["prob_fake"])
            item["known_token_ratio"] = float(item["known_token_ratio"])
            if item["rating"] is not None:
                item["rating"] = float(item["rating"])
            result.append(item)
        return result
    finally:
        cursor.close()


def count_reviews(connection, dataset_split=None):
    """Đếm số review, có thể lọc theo tập dữ liệu."""
    cursor = connection.cursor()
    try:
        if dataset_split is None:
            cursor.execute("SELECT count(*) FROM reviews")
        else:
            cursor.execute(
                "SELECT count(*) FROM reviews WHERE dataset_split = %s",
                (dataset_split,),
            )
        return int(cursor.fetchone()[0])
    finally:
        cursor.close()


def count_by_category(connection, dataset_split, model_run_id):
    """
    Đếm số review theo nhóm hiển thị.

    Đếm ở DB để đối chiếu độc lập với con số export_web_data.py tính ra. Hai
    cách tính khớp nhau mới đáng tin.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT category, count(*)
            FROM reviews
            WHERE dataset_split = %s AND model_run_id = %s AND batch_id IS NULL
            GROUP BY category
            """,
            (dataset_split, model_run_id),
        )
        return {row[0]: int(row[1]) for row in cursor.fetchall()}
    finally:
        cursor.close()


def cache_get(connection, source_hash):
    """
    Tra bản dịch đã lưu.

    Trả dict {translated_text, provider} hoặc None nếu chưa có.
    Đồng thời tăng hit_count để biết bản dịch nào được dùng nhiều.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT translated_text, provider, detected_language
            FROM translation_cache
            WHERE source_hash = %s
            """,
            (source_hash,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        cursor.execute(
            """
            UPDATE translation_cache
            SET hit_count = hit_count + 1, last_used_at = now()
            WHERE source_hash = %s
            """,
            (source_hash,),
        )
        connection.commit()

        return {
            "translated_text": row[0],
            "provider": row[1],
            "detected_language": row[2],
        }
    finally:
        cursor.close()


def cache_put(
    connection,
    source_hash,
    source_text,
    translated_text,
    provider,
    detected_language="",
):
    """
    Lưu một bản dịch mới.

    Nếu khóa đã tồn tại thì KHÔNG ghi đè bản dịch cũ, nhưng bổ sung
    detected_language nếu bản cũ còn trống. Cache tạo trước khi có cột này sẽ
    thiếu ngôn ngữ nguồn, làm bước kiểm tra dịch vòng bị bỏ qua mãi mãi.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO translation_cache (
                source_hash, source_text, translated_text, provider,
                detected_language
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_hash) DO UPDATE
                SET detected_language = EXCLUDED.detected_language
                WHERE translation_cache.detected_language = ''
            """,
            (
                source_hash,
                source_text,
                translated_text,
                provider,
                detected_language,
            ),
        )
        connection.commit()
    finally:
        cursor.close()


def is_available():
    """
    Kiểm tra nhanh DB có dùng được không, KHÔNG ném lỗi ra ngoài.

    Cần hàm này để trang web và API báo lỗi thân thiện khi người dùng quên bật
    Docker, thay vì sập cả chương trình.

    Lưu ý: hàm này gọi connect() nên có thể thử lại tới DB_CONNECT_ATTEMPTS lần.
    Đừng dùng nó cho đèn báo trạng thái (xem check_health).
    """
    try:
        connection = connect()
        connection.close()
        return True
    except Exception:
        return False


def check_health():
    """
    Kiểm tra trạng thái DB đúng MỘT lần, dùng cho đèn báo trên web.

    Không dùng is_available() ở đây vì connect() thử lại 15 lần, mỗi lần chờ
    tối đa 10 giây. Khi DB đã tắt, đèn báo sẽ treo rất lâu mỗi lần trình duyệt
    hỏi. Hàm này chỉ mở một kết nối với timeout ngắn rồi đóng ngay.

    Trả về dict:
        connected (bool)   : kết nối được hay không.
        latency_ms (float) : thời gian một lần kiểm tra, đơn vị mili giây.
        error (str)        : mô tả lỗi ngắn gọn, rỗng nếu thành công.
    """
    settings = get_settings()
    started_at = time.perf_counter()

    try:
        connection = pg8000.dbapi.connect(
            user=settings["user"],
            password=settings["password"],
            host=settings["host"],
            port=settings["port"],
            database=settings["database"],
            timeout=DB_HEALTH_TIMEOUT_SECONDS,
        )
        connection.close()
    except Exception as error:  # pg8000 ném nhiều loại lỗi khác nhau
        latency_ms = (time.perf_counter() - started_at) * 1000.0
        return {
            "connected": False,
            "latency_ms": round(latency_ms, 1),
            "error": str(error),
        }

    latency_ms = (time.perf_counter() - started_at) * 1000.0
    return {
        "connected": True,
        "latency_ms": round(latency_ms, 1),
        "error": "",
    }
