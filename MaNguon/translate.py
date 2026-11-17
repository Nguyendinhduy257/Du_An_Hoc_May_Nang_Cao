r"""
Dịch một câu sang tiếng Anh trước khi đưa vào model.

Nhận chuỗi văn bản (bất kỳ ngôn ngữ) và tùy chọn dùng cache trong PostgreSQL,
trả về translated_text, used_translation, error, provider và
detected_language.

Dùng urllib của thư viện chuẩn thay vì thư viện dịch để không phát sinh gói
mới, an toàn với Python 3.14.2.

Ba lớp cache, ưu tiên từ trên xuống: cache trong bộ nhớ (nhanh nhất, mất khi
tắt server), cache trong PostgreSQL (còn sau khi khởi động lại, dùng chung),
rồi mới gọi mạng (chậm nhất, có thể lỗi).

Ba nhà cung cấp thử lần lượt: Google translate_a/single (chất lượng tốt, tự
nhận diện ngôn ngữ), Google clients5 (endpoint khác, cũng tự nhận diện), và
MyMemory (cần biết ngôn ngữ nguồn nên chỉ dùng khi đã nhận diện được hoặc câu
có dấu tiếng Việt).

Các endpoint này là dịch vụ công khai không chính thức, không cam kết ổn định
và có thể bị chặn bất kỳ lúc nào; chỉ dùng cho demo đồ án.
"""

import difflib
import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from config import (
    TRANSLATE_GOOGLE_ALT_URL,
    TRANSLATE_GOOGLE_URL,
    TRANSLATE_MAX_ATTEMPTS,
    TRANSLATE_MYMEMORY_URL,
    TRANSLATE_RETRY_DELAY_SECONDS,
    TRANSLATE_TIMEOUT_SECONDS,
    TRANSLATION_CONSISTENCY_MAX_CHARS,
    TRANSLATION_PROVIDER_GOOGLE,
    TRANSLATION_PROVIDER_GOOGLE_ALT,
    TRANSLATION_PROVIDER_MYMEMORY,
)

# Thứ tự thử nhà cung cấp theo từng lần thử.
# Xen kẽ thay vì thử hết Google rồi mới sang MyMemory: nếu tên miền chính bị
# chặn, lần thử thứ hai đã đổi sang đường khác ngay, không phải chờ lâu.
PROVIDER_PLAN = [
    TRANSLATION_PROVIDER_GOOGLE,
    TRANSLATION_PROVIDER_GOOGLE_ALT,
    TRANSLATION_PROVIDER_MYMEMORY,
]

# TRANSLATION_CACHE: câu gốc -> kết quả đã dịch.
# Người dùng hay bấm lại cùng một nút mẫu. Gọi mạng lặp lại vừa chậm vừa dễ
# bị chặn vì quá nhiều request.
TRANSLATION_CACHE = {}

# Mỗi luồng giữ một kết nối PostgreSQL để tra cache.
# Mở kết nối mới tốn khoảng 110 ms. Một file 200 dòng sẽ mất hơn 20 giây chỉ
# giây chỉ để mở/đóng kết nối, dù bản dịch đã nằm sẵn trong cache. Dùng
# threading.local thay vì một biến chung vì server chạy đa luồng.
CACHE_CONNECTION = threading.local()


def open_cache_connection():
    """Trả kết nối cache của luồng hiện tại, mở mới nếu chưa có."""
    connection = getattr(CACHE_CONNECTION, "connection", None)
    if connection is None:
        import db

        connection = db.connect()
        CACHE_CONNECTION.connection = connection
    return connection


def close_cache_connection():
    """Đóng và quên kết nối cache của luồng hiện tại (dùng khi gặp lỗi)."""
    connection = getattr(CACHE_CONNECTION, "connection", None)
    CACHE_CONNECTION.connection = None
    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass

# Ký tự riêng của tiếng Việt, dùng để đoán ngôn ngữ nguồn khi Google lỗi.
# Cần vì MyMemory không nhận "auto": không đoán được thì không gọi được nó.
VIETNAMESE_CHARACTERS = "ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"


def normalize_for_compare(text):
    """Chuẩn hóa nhẹ để so câu gốc với câu dịch vòng."""
    if text is None:
        return ""
    return " ".join(str(text).lower().split())


def text_similarity(original_text, compared_text):
    """
    Đo độ tương đồng 0-1 giữa câu gốc và câu dịch vòng.

    Dùng SequenceMatcher vì nó so được cả trật tự ký tự, không phụ thuộc việc
    tách từ của từng ngôn ngữ. Chỉ so phần đầu để tránh tốn thời gian với câu
    rất dài.
    """
    left = normalize_for_compare(original_text)[:TRANSLATION_CONSISTENCY_MAX_CHARS]
    right = normalize_for_compare(compared_text)[:TRANSLATION_CONSISTENCY_MAX_CHARS]

    if left == "" or right == "":
        return 0.0

    return difflib.SequenceMatcher(None, left, right).ratio()


def guess_source_language(text):
    """
    Đoán ngôn ngữ nguồn khi nhà cung cấp không tự nhận diện.

    Chỉ đoán được tiếng Việt (nhờ ký tự có dấu). Trả chuỗi rỗng nếu không
    đoán được; khi đó MyMemory bị bỏ qua thay vì dịch sai ngôn ngữ.
    """
    for character in str(text):
        if character in VIETNAMESE_CHARACTERS:
            return "vi"
    return ""


def source_hash(text, target_language):
    """
    Băm câu gốc + ngôn ngữ đích thành khóa cache 64 ký tự hex.

    Khóa phải gồm ngôn ngữ đích vì cùng một câu tiếng Anh có thể được dịch
    sang tiếng Việt hoặc giữ nguyên tiếng Anh. Nếu chỉ băm câu, hai bản dịch
    khác ngôn ngữ sẽ ghi đè lên nhau trong cache.

    Băm thay vì dùng nguyên câu làm khóa vì câu dài có thể vài nghìn ký tự,
    làm khóa chính rất tốn chỗ và chậm. SHA-256 cố định 64 ký tự.
    """
    payload = target_language + "\n" + text
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_google_single_response(raw_body):
    """
    Bóc câu dịch từ JSON lồng nhau của endpoint translate_a/single.

    Dạng phản hồi:
        [ [ ["câu đã dịch 1", "câu gốc 1", ...], ["câu đã dịch 2", ...] ],
          null, "vi", ... ]
    Phần tử [2] là ngôn ngữ nguồn được nhận diện.
    """
    parsed = json.loads(raw_body)
    segments = parsed[0]

    pieces = []
    for segment in segments:
        if segment and segment[0]:
            pieces.append(segment[0])

    detected_language = ""
    if len(parsed) > 2 and isinstance(parsed[2], str):
        detected_language = parsed[2]

    translated_text = "".join(pieces).strip()
    if not translated_text:
        raise ValueError("phản hồi dịch rỗng")

    return {
        "translated_text": translated_text,
        "detected_language": detected_language,
    }


def request_google_once(text, target_language):
    """
    Gọi endpoint translate_a/single đúng MỘT lần.

    Tách riêng khỏi vòng thử lại để vòng lặp phía dưới dễ đọc.
    """
    # sl="auto": tự nhận diện ngôn ngữ nguồn; tl=<target_language>: ngôn ngữ đích.
    request_parameters = {
        "client": "gtx",
        "sl": "auto",
        "tl": target_language,
        "dt": "t",
        "q": text,
    }

    # Gửi bằng POST vì câu dài có thể vượt giới hạn độ dài URL.
    request_data = urllib.parse.urlencode(request_parameters).encode("utf-8")

    request = urllib.request.Request(
        TRANSLATE_GOOGLE_URL,
        data=request_data,
        headers={"User-Agent": "Mozilla/5.0 (fake-review-demo)"},
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=TRANSLATE_TIMEOUT_SECONDS
    ) as response:
        raw_body = response.read().decode("utf-8")

    return parse_google_single_response(raw_body)


def parse_google_alt_response(raw_body):
    """
    Bóc câu dịch từ endpoint clients5.

    Dạng phản hồi thường gặp:
        [ ["câu đã dịch", "vi"] ]
    Mỗi phần tử là một đoạn; phần tử [1] là ngôn ngữ nguồn.
    """
    parsed = json.loads(raw_body)

    pieces = []
    detected_language = ""

    if isinstance(parsed, list):
        for segment in parsed:
            if (
                isinstance(segment, list)
                and len(segment) > 0
                and isinstance(segment[0], str)
            ):
                pieces.append(segment[0])
                if (
                    detected_language == ""
                    and len(segment) > 1
                    and isinstance(segment[1], str)
                ):
                    detected_language = segment[1]

    translated_text = "".join(pieces).strip()
    if not translated_text:
        raise ValueError("phản hồi dịch rỗng")

    return {
        "translated_text": translated_text,
        "detected_language": detected_language,
    }


def request_google_alt_once(text, target_language):
    """Gọi endpoint clients5 của Google đúng MỘT lần."""
    request_url = (
        TRANSLATE_GOOGLE_ALT_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "client": "dict-chrome-ex",
                "sl": "auto",
                "tl": target_language,
            }
        )
    )

    request_data = urllib.parse.urlencode({"q": text}).encode("utf-8")
    request = urllib.request.Request(
        request_url,
        data=request_data,
        headers={
            "User-Agent": "Mozilla/5.0 (fake-review-demo)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=TRANSLATE_TIMEOUT_SECONDS
    ) as response:
        raw_body = response.read().decode("utf-8")

    return parse_google_alt_response(raw_body)


def request_mymemory_once(text, target_language, source_language):
    """
    Gọi MyMemory đúng MỘT lần.

    MyMemory yêu cầu biết ngôn ngữ nguồn (không nhận "auto"), nên hàm này
    chỉ được gọi khi đã có source_language.
    """
    if source_language == "":
        raise ValueError("MyMemory cần biết ngôn ngữ nguồn")

    # MyMemory giới hạn độ dài câu ở mức vài trăm ký tự; câu dài hơn nên
    # chuyển sang nhà cung cấp khác thay vì gửi một request chắc chắn lỗi.
    if len(text) > 500:
        raise ValueError("MyMemory chỉ nhận câu ngắn (tối đa 500 ký tự)")

    request_url = (
        TRANSLATE_MYMEMORY_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "q": text,
                "langpair": source_language + "|" + target_language,
            }
        )
    )

    request = urllib.request.Request(
        request_url,
        headers={"User-Agent": "Mozilla/5.0 (fake-review-demo)"},
        method="GET",
    )

    with urllib.request.urlopen(
        request, timeout=TRANSLATE_TIMEOUT_SECONDS
    ) as response:
        raw_body = response.read().decode("utf-8")

    parsed = json.loads(raw_body)

    # MyMemory trả mã lỗi trong JSON chứ không phải HTTP status.
    status = str(parsed.get("responseStatus", ""))
    if status != "200":
        raise ValueError("MyMemory báo lỗi: " + str(parsed.get("responseDetails", status)))

    translated_text = str(parsed.get("responseData", {}).get("translatedText", "")).strip()
    if not translated_text:
        raise ValueError("phản hồi dịch rỗng")

    return {
        "translated_text": translated_text,
        "detected_language": source_language,
    }


def lookup_database_cache(text, target_language, use_db_cache):
    """
    Tra cache trong PostgreSQL.

    Trả dict {translated_text, provider, detected_language} hoặc None.
    Mọi lỗi DB đều bị nuốt vì dịch thuật không được phép làm hỏng cả lần dự
    đoán chỉ vì database tạm thời không kết nối được.
    """
    if not use_db_cache:
        return None

    try:
        import db
    except Exception:
        return None

    # Thử hai lần: lần đầu dùng kết nối cũ (có thể đã bị server đóng), lần hai
    # mở kết nối mới. Nhờ vậy một file 200 dòng không phải mở 200 kết nối.
    for attempt in range(2):
        try:
            connection = open_cache_connection()
            return db.cache_get(connection, source_hash(text, target_language))
        except Exception:
            close_cache_connection()
    return None


def save_database_cache(
    text, target_language, translated_text, provider, detected_language, use_db_cache
):
    """Lưu bản dịch vào PostgreSQL; lỗi DB không được làm hỏng kết quả."""
    if not use_db_cache:
        return

    try:
        import db
    except Exception:
        return

    for attempt in range(2):
        try:
            connection = open_cache_connection()
            db.cache_put(
                connection,
                source_hash(text, target_language),
                text,
                translated_text,
                provider,
                detected_language,
            )
            return
        except Exception:
            close_cache_connection()


def translate_text(text, target_language="en", use_db_cache=True):
    """
    Dịch text sang ngôn ngữ đích, có thử lại và đổi nhà cung cấp khi lỗi.

    Trả về dict:
      translated_text   : câu đã dịch, hoặc câu gốc nếu tất cả đều lỗi.
      used_translation  : True nếu đã gọi dịch thành công.
      error             : thông báo lỗi, chuỗi rỗng nếu thành công.
      provider          : nhà cung cấp đã trả kết quả.
      detected_language : ngôn ngữ nguồn nhận diện được (rỗng nếu không biết).
    """
    # Khóa cache trong bộ nhớ phải gồm cả ngôn ngữ đích, cùng lý do như source_hash.
    memory_key = target_language + "\n" + text

    if memory_key in TRANSLATION_CACHE:
        # Trả bản sao để người gọi không vô tình sửa dữ liệu trong cache.
        return dict(TRANSLATION_CACHE[memory_key])

    # Lớp cache thứ hai: PostgreSQL. Cần lớp này vì endpoint công khai có thể
    # bị chặn; nếu đã từng dịch câu này thì vẫn trả được kết quả cũ.
    cached = lookup_database_cache(text, target_language, use_db_cache)
    if cached is not None:
        cached_language = cached.get("detected_language", "")

        # Cache tạo trước khi có cột detected_language sẽ trả chuỗi rỗng.
        # Đoán tại đây thay vì gọi mạng lại vì mục đích của cache là chịu được
        # lúc mất mạng; gọi lại chỉ để dò ngôn ngữ sẽ làm mất lợi ích đó.
        # Chỉ đoán được tiếng Việt; ngôn ngữ khác để trống và bỏ qua kiểm tra.
        if cached_language == "":
            cached_language = guess_source_language(text)
            if cached_language != "":
                save_database_cache(
                    text,
                    target_language,
                    cached["translated_text"],
                    cached.get("provider", ""),
                    cached_language,
                    use_db_cache,
                )

        result = {
            "translated_text": cached["translated_text"],
            "used_translation": True,
            "error": "",
            "provider": cached.get("provider", ""),
            "detected_language": cached_language,
        }
        TRANSLATION_CACHE[memory_key] = dict(result)
        return result

    last_error = None
    detected_language = ""

    for attempt in range(1, TRANSLATE_MAX_ATTEMPTS + 1):
        provider_name = PROVIDER_PLAN[(attempt - 1) % len(PROVIDER_PLAN)]

        try:
            if provider_name == TRANSLATION_PROVIDER_GOOGLE:
                payload = request_google_once(text, target_language)
            elif provider_name == TRANSLATION_PROVIDER_GOOGLE_ALT:
                payload = request_google_alt_once(text, target_language)
            else:
                source_language = detected_language
                if source_language == "":
                    source_language = guess_source_language(text)
                payload = request_mymemory_once(
                    text, target_language, source_language
                )

            if payload["detected_language"] != "":
                detected_language = payload["detected_language"]

            result = {
                "translated_text": payload["translated_text"],
                "used_translation": True,
                "error": "",
                "provider": provider_name,
                "detected_language": detected_language,
            }

            TRANSLATION_CACHE[memory_key] = dict(result)
            save_database_cache(
                text,
                target_language,
                payload["translated_text"],
                provider_name,
                detected_language,
                use_db_cache,
            )
            return result

        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            IndexError,
            TypeError,
            KeyError,
        ) as error:
            last_error = error

            # Chờ lâu dần giữa các lần thử: lần 1 chờ 0.6s, lần 2 chờ 1.2s...
            # Tăng dần vì nếu dịch vụ đang quá tải, thử lại ngay lập tức chỉ
            # làm tình hình tệ hơn.
            if attempt < TRANSLATE_MAX_ATTEMPTS:
                time.sleep(TRANSLATE_RETRY_DELAY_SECONDS * attempt)

    # Không để lỗi mạng làm hỏng cả lần dự đoán:
    # dùng câu gốc và ghi lại lỗi để lớp web hiện cảnh báo.
    # Không cache kết quả lỗi: mạng có lại thì lần sau phải thử lại.
    return {
        "translated_text": text,
        "used_translation": False,
        "error": f"Không dịch được sau {TRANSLATE_MAX_ATTEMPTS} lần thử: {last_error}",
        "provider": "",
        "detected_language": "",
    }


def translate_to_english(text, use_db_cache=True):
    """
    Dịch text sang tiếng Anh.

    Đây là hàm mà API và lớp phân tích file dùng; giữ tên cũ để không phải sửa
    nơi gọi. Toàn bộ logic nằm trong translate_text.
    """
    return translate_text(text, target_language="en", use_db_cache=use_db_cache)


def translate_to_language(text, target_language, use_db_cache=True):
    """Dịch sang một ngôn ngữ bất kỳ; dùng cho bước dịch vòng kiểm tra nghĩa."""
    return translate_text(
        text, target_language=target_language, use_db_cache=use_db_cache
    )
