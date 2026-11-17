r"""
Gắn cờ và xếp nhóm hiển thị cho từng review, kèm lý do đọc được.

Lưu ý về dữ liệu: dataset gốc chỉ có nhãn máy sinh (CG) và người viết (OR),
không có nhãn bot, boost hay spam. Năm nhóm hiển thị là luật suy luận, không
phải nhãn ground truth và không phải thuật toán thứ hai, nên báo cáo không
được ghi "model phát hiện bot với độ chính xác X%".

Hai trường được tách riêng cho dễ tra: category_basis nói nhóm do model hay
do luật quyết định; reason_codes chỉ giữ mã lý do và vài tham số, câu tiếng
Việt được ghép từ REASON_TEMPLATES ở một chỗ. Lưu cả câu cho từng dòng sẽ làm
file dữ liệu phình rất nhanh vì cùng một lý do lặp hàng nghìn lần.
"""

from config import (
    BOT_MAX_WORDS,
    CATEGORY_BOT_BOOST,
    CATEGORY_DUPLICATE,
    CATEGORY_FAKE,
    CATEGORY_GENUINE,
    CATEGORY_LOW_CONTENT,
    CATEGORY_ORDER,
    MIN_KNOWN_TOKEN_RATIO,
    MIN_USEFUL_WORDS,
    TRANSLATION_BORDERLINE_MARGIN,
    TRANSLATION_CONSISTENCY_MIN_SIMILARITY,
)

# Mẫu câu giải thích, dùng chung cho API và web.
# Để ở đây để chỉ có một nơi định nghĩa câu chữ. Web nhận bảng mẫu này trong
# data_meta.js rồi tự thay {0}, {1}... nên không phải chép lại câu.
REASON_TEMPLATES = {
    "low_confidence": (
        "Chỉ {0} token có trong từ vựng model, dưới mức {1} nên kết quả "
        "không đáng tin."
    ),
    "low_content": (
        "Chỉ có {0} từ, dưới mức {1} từ nên không đủ thông tin để đánh giá."
    ),
    "duplicate": (
        "Trùng khít với một review phía trước sau khi chuẩn hóa chữ thường "
        "và khoảng trắng."
    ),
    "bot_boost": (
        "Model cho xác suất giả {0} (ngưỡng {1}), lại đúng 5 sao và chỉ "
        "{2} từ (tối đa {3})."
    ),
    "fake": (
        "Model cho xác suất giả {0}, cao hơn ngưỡng {1}."
    ),
    "genuine": (
        "Model cho xác suất giả {0}, thấp hơn ngưỡng {1}."
    ),
    "has_link": "Có đường dẫn trong nội dung (chỉ là cờ cảnh báo).",
    "translation_borderline": (
        "Câu đã qua dịch máy và xác suất giả {0} nằm sát ngưỡng {1} "
        "(biên ±{2}) nên kết luận không ổn định."
    ),
    "translation_inconsistent": (
        "Dịch vòng không khớp câu gốc (tương đồng {0}, dưới mức {1}) nên "
        "bản dịch có thể đã làm sai nghĩa."
    ),
}


def normalize_text(text):
    """
    Chuẩn hóa text để so trùng lặp: chữ thường + gộp mọi khoảng trắng.

    Hai review copy-paste có thể khác nhau ở dấu cách hoặc xuống dòng; không
    chuẩn hóa thì không phát hiện được.
    """
    if text is None:
        return ""
    return " ".join(str(text).lower().split())


def count_words(text):
    """Đếm số từ sau khi chuẩn hóa."""
    return len(normalize_text(text).split())


def has_link(text):
    """
    Đoán xem review có chứa đường dẫn quảng cáo hay không.

    Đây chỉ là CỜ CẢNH BÁO, không phải nhóm chính: review thật cũng có thể
    dẫn link sản phẩm. Vì vậy không dùng nó để kết luận spam một mình.
    """
    lower_text = str(text).lower()
    return (
        "http://" in lower_text
        or "https://" in lower_text
        or "www." in lower_text
    )


def is_five_star(rating):
    """Trả True nếu rating đúng bằng 5.0; thiếu hoặc sai định dạng -> False."""
    if rating is None:
        return False
    try:
        return float(rating) == 5.0
    except (TypeError, ValueError):
        return False


def format_percent(value):
    """Đổi tỷ lệ 0-1 thành chuỗi phần trăm, ví dụ 0.4571 -> '45.7%'."""
    return f"{float(value) * 100:.1f}%"


def category_basis_for_category(category):
    """
    Cho biết nhóm này do MODEL, do LUẬT, hay do cả hai quyết định.

    Tách hàm riêng vì export_web_data.py cần cùng câu trả lời cho dữ liệu đọc
    từ DB. Một nơi định nghĩa, hai nơi dùng, tránh lệch nhau khi bảo trì.
    """
    if category in (CATEGORY_LOW_CONTENT, CATEGORY_DUPLICATE):
        return "rule"
    if category == CATEGORY_BOT_BOOST:
        return "model+rule"
    return "model"


def flag_source_for_category(category):
    """
    Nhãn nguồn ngắn gọn để hiển thị: "rule" hoặc "model".

    Nhóm bot/boost là "model+rule" nhưng vẫn có model tham gia, nên nguồn cờ
    được ghi là "model"; phần chữ trên web sẽ hiện đầy đủ "MODEL + LUẬT".
    """
    if category_basis_for_category(category) == "rule":
        return "rule"
    return "model"


def render_reason(code_entry):
    """
    Ghép một reason_code thành câu tiếng Việt.

    code_entry có dạng [mã, tham số 0, tham số 1, ...].
    Nếu mã lạ (dữ liệu cũ), trả lại chính mã để không làm mất thông tin.
    """
    code = code_entry[0]
    template = REASON_TEMPLATES.get(code)
    if template is None:
        return str(code)

    text = template
    parameters = code_entry[1:]
    for index in range(len(parameters)):
        text = text.replace("{" + str(index) + "}", str(parameters[index]))
    return text


def build_reason_codes(
    category,
    probability_fake,
    threshold,
    word_count,
    known_token_ratio,
    is_reliable,
    has_link_flag,
    used_translation=False,
    translation_similarity=None,
):
    """
    Sinh danh sách reason_code theo đúng thứ tự hiển thị.

    Thứ tự: lý do tin cậy -> lý do xếp nhóm -> cờ phụ -> cờ do dịch máy.
    Lý do tin cậy đứng đầu vì nó ảnh hưởng mạnh nhất tới kết luận.
    """
    codes = []

    if not is_reliable:
        codes.append(
            [
                "low_confidence",
                format_percent(known_token_ratio),
                format_percent(MIN_KNOWN_TOKEN_RATIO),
            ]
        )

    if category == CATEGORY_LOW_CONTENT:
        codes.append(["low_content", word_count, MIN_USEFUL_WORDS])
    elif category == CATEGORY_DUPLICATE:
        codes.append(["duplicate"])
    elif category == CATEGORY_BOT_BOOST:
        codes.append(
            [
                "bot_boost",
                format_percent(probability_fake),
                format_percent(threshold),
                word_count,
                BOT_MAX_WORDS,
            ]
        )
    elif category == CATEGORY_FAKE:
        codes.append(
            ["fake", format_percent(probability_fake), format_percent(threshold)]
        )
    else:
        codes.append(
            ["genuine", format_percent(probability_fake), format_percent(threshold)]
        )

    if has_link_flag:
        codes.append(["has_link"])

    if used_translation and abs(probability_fake - threshold) <= TRANSLATION_BORDERLINE_MARGIN:
        codes.append(
            [
                "translation_borderline",
                format_percent(probability_fake),
                format_percent(threshold),
                format_percent(TRANSLATION_BORDERLINE_MARGIN),
            ]
        )

    if (
        translation_similarity is not None
        and translation_similarity < TRANSLATION_CONSISTENCY_MIN_SIMILARITY
    ):
        codes.append(
            [
                "translation_inconsistent",
                format_percent(translation_similarity),
                format_percent(TRANSLATION_CONSISTENCY_MIN_SIMILARITY),
            ]
        )

    return codes


def classify_review(
    text,
    probability_fake,
    threshold,
    rating,
    is_duplicate,
    known_token_ratio=1.0,
    used_translation=False,
    translation_similarity=None,
):
    """
    Xếp một review vào đúng MỘT nhóm chính, theo thứ tự ưu tiên:

        1. Quá ngắn / rỗng        -> low_content
        2. Trùng khít bài trước   -> spam_duplicate
        3. Máy sinh + 5 sao + ngắn -> suspected_bot_boost
        4. Máy sinh               -> suspected_fake
        5. Còn lại                -> genuine

    Ưu tiên theo thứ tự này vì một review rỗng không thể là "review thật hữu
    ích" dù model cho xác suất nào; và không nên gọi một câu copy-paste là
    "giả" khi bản chất vấn đề là trùng lặp.

    known_token_ratio: tỷ lệ token của câu nằm trong từ vựng TF-IDF đã học.
    Câu có tỷ lệ thấp là câu model "không hiểu", nên bị đánh dấu không đáng tin.

    used_translation / translation_similarity: thông tin về bước dịch máy.
    Câu đã dịch mà xác suất sát ngưỡng, hoặc dịch vòng lệch nghĩa, sẽ bị gắn
    cờ và KHÔNG được coi là hữu ích.
    """
    word_count = count_words(text)

    # Tỷ lệ token quen thuộc do nơi gọi truyền vào; thiếu thì coi như đủ tin cậy.
    ratio = 1.0 if known_token_ratio is None else float(known_token_ratio)
    is_reliable = ratio >= MIN_KNOWN_TOKEN_RATIO

    link_flag = has_link(text)
    translation_borderline = (
        bool(used_translation)
        and abs(float(probability_fake) - float(threshold))
        <= TRANSLATION_BORDERLINE_MARGIN
    )
    translation_inconsistent = (
        translation_similarity is not None
        and float(translation_similarity) < TRANSLATION_CONSISTENCY_MIN_SIMILARITY
    )

    flags = []
    if word_count < MIN_USEFUL_WORDS:
        flags.append("low_content")
    if is_duplicate:
        flags.append("duplicate")
    if link_flag:
        flags.append("has_link")
    if is_five_star(rating):
        flags.append("five_star")
    if probability_fake >= threshold:
        flags.append("model_fake")
    if not is_reliable:
        flags.append("low_confidence")
    if translation_borderline:
        flags.append("translation_borderline")
    if translation_inconsistent:
        flags.append("translation_inconsistent")

    if word_count < MIN_USEFUL_WORDS:
        category = CATEGORY_LOW_CONTENT
    elif is_duplicate:
        category = CATEGORY_DUPLICATE
    elif probability_fake >= threshold:
        if is_five_star(rating) and word_count <= BOT_MAX_WORDS:
            category = CATEGORY_BOT_BOOST
        else:
            category = CATEGORY_FAKE
    else:
        category = CATEGORY_GENUINE

    reason_codes = build_reason_codes(
        category=category,
        probability_fake=probability_fake,
        threshold=threshold,
        word_count=word_count,
        known_token_ratio=ratio,
        is_reliable=is_reliable,
        has_link_flag=link_flag,
        used_translation=used_translation,
        translation_similarity=translation_similarity,
    )
    reasons = [render_reason(code_entry) for code_entry in reason_codes]

    return {
        "primary_category": category,
        "category_basis": category_basis_for_category(category),
        "flags": flags,
        "reasons": reasons,
        "reason_codes": reason_codes,
        "flag_source": flag_source_for_category(category),
        "word_count": word_count,
        # Lưu tỷ lệ token quen thuộc để web ghép lại đúng lý do "không đáng tin"
        # mà không phải đọc CSV gốc hay tính lại.
        "known_token_ratio": ratio,
        # Review chỉ được coi là hữu ích khi vừa là genuine, vừa đủ tin cậy,
        # vừa không bị nghi do bước dịch máy làm lệch kết luận.
        "is_reliable": is_reliable,
        "translation_borderline": translation_borderline,
        "translation_inconsistent": translation_inconsistent,
        "is_useful": (
            category == CATEGORY_GENUINE
            and is_reliable
            and not translation_borderline
            and not translation_inconsistent
        ),
    }


def star_index(rating):
    """
    Đổi rating 1.0-5.0 thành chỉ số 0-4 cho mảng đếm sao.

    Trả None nếu rating thiếu, không phải số, là NaN, hoặc ngoài khoảng 1-5.
    Không dùng pandas ở đây vì module này còn được API dùng, không cần kéo
    pandas vào chỉ để kiểm tra NaN.
    """
    if rating is None:
        return None

    try:
        value = float(rating)
    except (TypeError, ValueError):
        return None

    # NaN là giá trị không bằng chính nó.
    if value != value:
        return None

    rounded = int(round(value))
    if rounded < 1 or rounded > 5:
        return None
    return rounded - 1


def build_summary(rows):
    """
    Tổng hợp số lượng theo nhóm và theo số sao.

    rows: danh sách dict, mỗi dict phải có:
        "category"    : một trong CATEGORY_ORDER
        "rating"      : 1.0-5.0 hoặc None
        "is_useful"   : True/False
        "is_reliable" : True/False

    star_all / star_useful là mảng 5 phần tử, chỉ số 0 = 1 sao ... 4 = 5 sao.
    Dùng mảng vì JSON giữ nguyên thứ tự, phía JS dễ vẽ 5 hàng.
    """
    categories = {}
    for category_id in CATEGORY_ORDER:
        categories[category_id] = 0

    star_all = [0, 0, 0, 0, 0]
    star_useful = [0, 0, 0, 0, 0]
    star_missing_all = 0
    star_missing_useful = 0
    useful_count = 0
    unreliable_count = 0

    for row in rows:
        category_id = row["category"]
        if category_id in categories:
            categories[category_id] = categories[category_id] + 1

        is_useful = bool(row["is_useful"])
        if is_useful:
            useful_count = useful_count + 1

        if not bool(row.get("is_reliable", True)):
            unreliable_count = unreliable_count + 1

        index = star_index(row.get("rating"))
        if index is None:
            star_missing_all = star_missing_all + 1
            if is_useful:
                star_missing_useful = star_missing_useful + 1
        else:
            star_all[index] = star_all[index] + 1
            if is_useful:
                star_useful[index] = star_useful[index] + 1

    total = len(rows)

    return {
        "total": total,
        "categories": categories,
        "useful_count": useful_count,
        "removed_count": total - useful_count,
        "unreliable_count": unreliable_count,
        "star_all": star_all,
        "star_useful": star_useful,
        "star_missing_all": star_missing_all,
        "star_missing_useful": star_missing_useful,
    }
