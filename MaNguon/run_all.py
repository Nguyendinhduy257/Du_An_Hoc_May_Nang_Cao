r"""
Chạy toàn bộ quy trình trong README mục 3 bằng một lệnh.

Mặc định chỉ chạy lại phần đã cũ; --full chạy lại từ đầu. Nó không tự tạo báo
cáo mà gọi các script con cập nhật MoHinh/, KetQuaChay/, DuLieuDemo/. Riêng nó ghi
KetQuaChay/run_state.json để nhớ lần chạy trước; file này xoá được bất cứ lúc nào.

Chạy:
    python MaNguon\run_all.py                 chỉ chạy phần đã cũ
    python MaNguon\run_all.py --check         chỉ báo cáo, không chạy gì
    python MaNguon\run_all.py --full          chạy lại tất cả
    python MaNguon\run_all.py --no-network    bỏ bước đo lệch dịch máy
    python MaNguon\run_all.py --no-notebook   bỏ notebook
    python MaNguon\run_all.py --check --full  xem trước một lần chạy đầy đủ

Các bước bám đúng README mục 3 (1, 2a, 2b, 3, 4, 6a, 6b, 7a, 7b). Bước 5 là
chạy web, tiến trình chạy mãi không tự kết thúc, nên để cho
ThuMucKhoiChay\2_Chay_Web.bat hoặc 4_Chay_Tat_Ca.bat.

Mặc định không chạy lại tất vì huấn luyện lại sinh thêm một dòng model_runs và
đổi data_meta.js, tạo "lịch sử giả" khó truy nguyên; bước đo lệch dịch gọi
dịch vụ công khai, mạng lỗi là báo cáo không so sánh được với lần trước;
notebook chạy lại mất hơn một phút và thay toàn bộ output đã lưu.

So dấu vết nội dung (fingerprint) thay vì ngày sửa file: các script chỉ ghi
file khi nội dung thật sự đổi, nên sau một lần chạy không đổi gì thì train.csv
vẫn giữ ngày sửa cũ còn data.py mang ngày mới, so theo ngày sẽ luôn kết luận
"đã cũ" và chạy lại mãi. Dấu vết nội dung còn đúng khi copy dự án sang máy
khác, nơi ngày sửa bị thay đổi.

Quy ước trong file: assess là hàm () -> (cần_chạy, lý_do), chỉ đọc trạng thái;
action là hàm () -> None, ném SystemExit nếu bước thất bại; inputs là các file
mà nội dung của chúng quyết định kết quả của bước.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import db
from config import (
    BASELINE_COMPARISON_JSON_PATH,
    DB_CONTAINER_NAME,
    DEPLOY_DIR,
    HEURISTIC_AUDIT_JSON_PATH,
    METRICS_JSON_PATH,
    MODEL_PATH,
    NOTEBOOK_PATH,
    PROJECT_ROOT,
    RAW_CSV_PATH,
    RESULTS_DIR,
    TEST_CSV_PATH,
    THRESHOLD_COST_JSON_PATH,
    TRAIN_CSV_PATH,
    TRANSLATION_BIAS_JSON_PATH,
    VAL_CSV_PATH,
)
from file_safety import sha256_of_bytes

# SOURCE_DIR: thư mục chứa các script con. Các script đó import "config" trần,
# nên phải được gọi từ đúng thư mục này (xem README mục 3, điểm 7).
SOURCE_DIR = Path(__file__).resolve().parent

# Bộ nhớ đệm của chính run_all.py, KHÔNG phải báo cáo của đồ án.
# Đặt trong KetQuaChay/ vì mọi thứ sinh tự động đã nằm ở đó, không làm bẩn thư mục
# gốc. Xóa file này chỉ làm lần chạy sau chạy lại nhiều hơn, không hỏng gì.
STATE_PATH = RESULTS_DIR / "run_state.json"

# Danh sách đầu vào của từng bước, khai báo tay thay vì quét cả thư mục.
# Không quét thư mục vì quét sẽ coi chính run_all.py là đầu vào, khiến lần
# chạy sau luôn thấy "đã cũ" và chạy lại mọi thứ.
SPLIT_INPUTS = [RAW_CSV_PATH, SOURCE_DIR / "data.py", SOURCE_DIR / "config.py"]
TRAIN_INPUTS = [
    TRAIN_CSV_PATH,
    VAL_CSV_PATH,
    SOURCE_DIR / "features.py",
    SOURCE_DIR / "train_baseline.py",
    SOURCE_DIR / "config.py",
]
MODEL_INPUTS = [METRICS_JSON_PATH, MODEL_PATH, SOURCE_DIR / "config.py"]


def file_fingerprint(paths):
    """
    Trả về chuỗi hex đại diện cho nội dung của một nhóm file.

    Có tên file trong dấu vết để đổi tên file cũng làm dấu vết đổi. File thiếu
    được ghi là "<missing>" thay vì bỏ qua, nhờ vậy xóa một file đầu vào cũng
    làm bước đó chạy lại.
    """
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes() if path.exists() else b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def load_state():
    """Đọc bộ nhớ đệm; file hỏng hoặc thiếu đều coi như rỗng (chạy lại hết)."""
    if not STATE_PATH.exists():
        return {}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    fingerprints = state.get("fingerprints")
    return fingerprints if isinstance(fingerprints, dict) else {}


def save_state(fingerprints):
    """
    Ghi bộ nhớ đệm.

    Không dùng file_safety.save_text_with_warning vì file này đổi mỗi khi đầu
    vào đổi, đó chính là việc của nó. Cảnh báo ghi đè ở đây sẽ kêu trên mọi
    lần chạy hợp lệ và làm người đọc quen với việc bỏ qua cảnh báo.
    """
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "fingerprints": fingerprints}
    STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def db_connection_reason():
    """
    Cho biết có phải bật container PostgreSQL không.

    Dùng check_health() (một lần thử, timeout 2 giây) chứ không dùng
    is_available() (thử lại 15 lần): khi Docker tắt, is_available() mất
    khoảng 30 giây mới trả lời, quá chậm cho một bước chỉ để "bật DB".
    """
    health = db.check_health()
    if not health["connected"]:
        return True, "chưa kết nối được PostgreSQL"
    return False, f"PostgreSQL đã sẵn sàng ({health['latency_ms']:.1f} ms)"


def db_sync_reason():
    """
    Cho biết PostgreSQL đã chứa đúng model hiện tại chưa.

    So mã băm của baseline_metrics.json vì đó chính là cách load_db.py quyết
    định tạo hay dùng lại dòng model_runs, nên hai bên luôn khớp nhau.
    """
    if not METRICS_JSON_PATH.exists():
        return True, f"chưa có {METRICS_JSON_PATH.name}"

    health = db.check_health()
    if not health["connected"]:
        return True, "chưa kết nối được PostgreSQL"

    connection = db.connect()
    try:
        latest = db.get_latest_model_run(connection)
        if latest is None:
            return True, "bảng model_runs đang trống"

        stored_hash = (latest.get("config") or {}).get("metrics_sha256")
        current_hash = sha256_of_bytes(METRICS_JSON_PATH.read_bytes())
        if stored_hash != current_hash:
            return True, "số liệu model đã đổi, DB còn bản cũ"

        if (
            db.count_reviews(connection, "test") == 0
            or db.count_reviews(connection, "val") == 0
        ):
            return True, "DB thiếu review test hoặc val"

        return False, f"DB khớp model_runs id={latest['id']}"
    finally:
        connection.close()


def web_data_reason():
    """
    Hỏi thẳng export_web_data.py --check thay vì tự so sánh.

    Không tự so vì chỉ script đó biết cách dựng lại nội dung hai file JS từ
    DB. Chép lại logic ở đây là tạo nguồn sự thật thứ hai, sớm muộn cũng lệch.
    """
    # Kiểm tra DB trước: khi DB tắt, --check cũng thất bại, nhưng lý do thật là
    # "chưa nối được DB" chứ không phải "file JS lệch".
    health = db.check_health()
    if not health["connected"]:
        return True, "chưa kết nối được PostgreSQL"

    result = subprocess.run(
        [sys.executable, str(SOURCE_DIR / "export_web_data.py"), "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        # Chỉ rõ utf-8 vì script con in tiếng Việt. Trên Windows, text=True một
        # mình sẽ giải mã bằng cp1252 và ném UnicodeDecodeError.
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return False, "hai file trong DuLieuDemo/ đã khớp DB"

    # Lấy dòng cuối của script con để lý do hiện ra cụ thể, không đoán.
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    detail = lines[-1].strip() if lines else "không rõ lý do"
    return True, f"DuLieuDemo/ đang lệch so với DB ({detail})"


def run_script(file_name):
    """Chạy một script con bằng đúng trình Python đang chạy run_all.py."""
    result = subprocess.run(
        [sys.executable, str(SOURCE_DIR / file_name)],
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"\nDỪNG: {file_name} trả mã lỗi {result.returncode}. "
            "Xem thông báo phía trên rồi chạy lại."
        )


def run_split():
    """Chạy data.py rồi báo lỗi ngay nếu vẫn thiếu file chia."""
    run_script("data.py")
    for path in (TRAIN_CSV_PATH, VAL_CSV_PATH, TEST_CSV_PATH):
        if not path.exists():
            raise SystemExit(
                f"data.py không tạo ra {path.name}. Dừng để tránh sai tiếp."
            )


def start_container():
    """Bật container PostgreSQL và chờ tới khi healthcheck báo healthy."""
    try:
        up = subprocess.run(["docker", "compose", "up", "-d"], cwd=DEPLOY_DIR)
    except FileNotFoundError:
        raise SystemExit(
            "Không tìm thấy lệnh docker. Hãy mở Docker Desktop rồi chạy lại."
        )

    if up.returncode != 0:
        raise SystemExit(
            "docker compose up -d thất bại.\n"
            "Kiểm tra: Docker Desktop đã mở chưa, và cổng trong "
            "ThuMucChienKhai\\.env có bị chương trình khác chiếm không."
        )

    # Chờ tối đa 30 x 2 giây. Có giới hạn để không treo vô hạn khi image lỗi.
    for _ in range(30):
        inspect = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                DB_CONTAINER_NAME,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if inspect.returncode == 0 and inspect.stdout.strip() == "healthy":
            print(f"[DB] {DB_CONTAINER_NAME} đã healthy.")
            return
        time.sleep(2)

    raise SystemExit(
        "Container chưa healthy sau 60 giây. Xem: docker compose logs db"
    )


def run_benchmark():
    """
    Chạy ba script của bước 7a.

    from_scratch.py không ghi file, nên chạy kèm ở đây như một phép tự kiểm
    tra công thức trước khi tin hai báo cáo bên dưới.
    """
    run_script("from_scratch.py")
    run_script("compare_baselines.py")
    run_script("threshold_cost_table.py")


def run_notebook():
    """
    Thực thi Notebook/from_scratch_gd_lr.ipynb tại chỗ.

    Import muộn để --check không cần nbformat/nbclient; máy thiếu gói đó chỉ
    hỏng đúng bước này chứ không hỏng cả quy trình.
    """
    import nbformat
    from nbclient import NotebookClient

    print(
        f"[CẢNH BÁO GHI ĐÈ] {NOTEBOOK_PATH.name}: "
        "toàn bộ output đã lưu sẽ bị thay bằng kết quả vừa chạy."
    )

    notebook = nbformat.read(NOTEBOOK_PATH, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=900,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOK_PATH.parent)}},
    )
    client.execute()
    nbformat.write(notebook, NOTEBOOK_PATH)


class Runner:
    """In tiến độ, quyết định chạy hay bỏ qua, và giữ bộ nhớ đệm."""

    def __init__(self, check_only, force):
        self.check_only = check_only
        self.force = force
        self.done = []
        self.skipped = []
        self.fingerprints = load_state()

    def cache_reason(self, cache_key, inputs, outputs):
        """
        Quyết định theo nội dung: file kết quả đủ chưa, đầu vào có đổi không.

        Trả (cần_chạy, lý_do) như mọi hàm assess khác.
        """
        for path in outputs:
            if not path.exists():
                return True, f"chưa có {path.name}"

        expected = file_fingerprint(inputs)
        stored = self.fingerprints.get(cache_key)
        if stored is None:
            return True, "chưa có dấu vết lần chạy trước"
        if stored != expected:
            return True, "nội dung file nguồn đã đổi"

        return False, "file nguồn không đổi từ lần chạy trước"

    def remember(self, cache_key, inputs):
        """Ghi dấu vết đầu vào ngay sau khi bước chạy xong, để ngắt giữa được."""
        self.fingerprints[cache_key] = file_fingerprint(inputs)
        save_state(self.fingerprints)

    def step(self, number, title, assess, action, cache_key=None, inputs=None):
        """
        Chạy một bước.

        number    : số bước theo README, ví dụ "2a".
        assess    : hàm () -> (cần_chạy, lý_do).
        action    : hàm () -> None, ném lỗi nếu bước thất bại.
        cache_key : khóa trong run_state.json; None = bước luôn tự kiểm tra.
        inputs    : danh sách file đầu vào, chỉ dùng khi có cache_key.
        """
        if self.force:
            needed, reason = True, "chế độ --full"
        else:
            needed, reason = assess()

        label = f"BƯỚC {number} - {title}"
        summary = f"{number}. {title}"

        if not needed:
            print(f"[BỎ QUA] {label}: {reason}")
            self.skipped.append(summary)
            return

        if self.check_only:
            print(f"[CẦN CHẠY] {label}: {reason}")
            self.done.append(summary)
            return

        print("=" * 70)
        print(label)
        print(f"    Lý do: {reason}")
        print("=" * 70)

        started_at = time.perf_counter()
        action()
        seconds = time.perf_counter() - started_at

        if cache_key is not None:
            self.remember(cache_key, inputs)

        print(f"[XONG] {label} ({seconds:.1f} giây)\n")
        self.done.append(summary)


def main():
    # Bật line buffering vì khi chạy qua .bat hoặc bị chuyển hướng, Python đệm
    # stdout theo khối, còn script con ghi thẳng ra console. Không bật thì tiêu
    # đề "BƯỚC ..." hiện SAU phần in của script con, rất khó đọc.
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(
        description="Chạy toàn bộ quy trình dự án bằng một lệnh."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="chỉ báo cáo bước nào cần chạy, không thực thi",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="chạy lại tất cả, bỏ qua kiểm tra đã cũ",
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="bỏ bước đo độ lệch dịch máy (bước này gọi dịch vụ công khai)",
    )
    parser.add_argument(
        "--no-notebook",
        action="store_true",
        help="bỏ bước chạy lại notebook",
    )
    arguments = parser.parse_args()

    runner = Runner(check_only=arguments.check, force=arguments.full)

    # --- Bước 1: PostgreSQL -------------------------------------------------
    runner.step(1, "Bật PostgreSQL", db_connection_reason, start_container)

    # --- Bước 2a: chia dữ liệu ---------------------------------------------
    # README gộp việc chia dữ liệu vào bước 2; tách ra vì data.py chạy trước
    # train_baseline.py và có đầu vào riêng (chỉ dữ liệu gốc).
    runner.step(
        2,
        "Chia dữ liệu train/val/test (a)",
        lambda: runner.cache_reason(
            "2a", SPLIT_INPUTS, [TRAIN_CSV_PATH, VAL_CSV_PATH, TEST_CSV_PATH]
        ),
        run_split,
        cache_key="2a",
        inputs=SPLIT_INPUTS,
    )

    # --- Bước 2b: huấn luyện ------------------------------------------------
    runner.step(
        2,
        "Huấn luyện + hiệu chuẩn + chọn ngưỡng (b)",
        lambda: runner.cache_reason(
            "2b", TRAIN_INPUTS, [MODEL_PATH, METRICS_JSON_PATH]
        ),
        lambda: run_script("train_baseline.py"),
        cache_key="2b",
        inputs=TRAIN_INPUTS,
    )

    # --- Bước 3: nạp PostgreSQL --------------------------------------------
    # Không dùng bộ nhớ đệm: phải hỏi thẳng database, vì ai đó có thể đã xóa
    # hoặc phục hồi dữ liệu mà file trên đĩa không đổi.
    runner.step(
        3,
        "Nạp dữ liệu vào PostgreSQL",
        db_sync_reason,
        lambda: run_script("load_db.py"),
    )

    # --- Bước 4: xuất dữ liệu cho web --------------------------------------
    runner.step(
        4,
        "Xuất dữ liệu cho web (DuLieuDemo/)",
        web_data_reason,
        lambda: run_script("export_web_data.py"),
    )

    # --- Bước 6a: kiểm chứng luật phân nhóm --------------------------------
    audit_inputs = MODEL_INPUTS + [
        SOURCE_DIR / "classify.py",
        SOURCE_DIR / "audit_heuristics.py",
    ]
    runner.step(
        6,
        "Kiểm chứng luật phân nhóm (a)",
        lambda: runner.cache_reason(
            "6a", audit_inputs, [HEURISTIC_AUDIT_JSON_PATH]
        ),
        lambda: run_script("audit_heuristics.py"),
        cache_key="6a",
        inputs=audit_inputs,
    )

    # --- Bước 6b: đo độ lệch do dịch máy -----------------------------------
    bias_inputs = [METRICS_JSON_PATH] + [
        SOURCE_DIR / "measure_translation_bias.py",
        SOURCE_DIR / "translate.py",
        SOURCE_DIR / "config.py",
    ]

    def translation_bias_assess():
        if arguments.no_network:
            return False, "đã tắt bằng --no-network"
        return runner.cache_reason(
            "6b", bias_inputs, [TRANSLATION_BIAS_JSON_PATH]
        )

    runner.step(
        6,
        "Đo độ lệch do dịch máy (b)",
        translation_bias_assess,
        lambda: run_script("measure_translation_bias.py"),
        cache_key="6b",
        inputs=bias_inputs,
    )

    # --- Bước 7a: minh hoạ + so sánh baseline ------------------------------
    benchmark_inputs = MODEL_INPUTS + [
        SOURCE_DIR / "compare_baselines.py",
        SOURCE_DIR / "threshold_cost_table.py",
        SOURCE_DIR / "from_scratch.py",
    ]
    runner.step(
        7,
        "Minh hoạ from-scratch + so sánh baseline (a)",
        lambda: runner.cache_reason(
            "7a",
            benchmark_inputs,
            [BASELINE_COMPARISON_JSON_PATH, THRESHOLD_COST_JSON_PATH],
        ),
        run_benchmark,
        cache_key="7a",
        inputs=benchmark_inputs,
    )

    # --- Bước 7b: notebook --------------------------------------------------
    # Không lấy notebook làm đầu vào: nó chính là file kết quả, đưa vào sẽ
    # khiến lần chạy sau luôn thấy "đã đổi" và chạy lại mãi.
    notebook_inputs = [SOURCE_DIR / "from_scratch.py", SOURCE_DIR / "config.py"]

    def notebook_assess():
        if arguments.no_notebook:
            return False, "đã tắt bằng --no-notebook"
        return runner.cache_reason("7b", notebook_inputs, [NOTEBOOK_PATH])

    runner.step(
        7,
        "Chạy lại notebook minh hoạ (b)",
        notebook_assess,
        run_notebook,
        cache_key="7b",
        inputs=notebook_inputs,
    )

    # --- Tổng kết -----------------------------------------------------------
    print("=" * 70)
    print("TỔNG KẾT")
    print("=" * 70)

    if runner.done:
        tag = "CẦN CHẠY" if arguments.check else "ĐÃ CHẠY"
        for item in runner.done:
            print(f"  [{tag:<8}] {item}")
    else:
        print("  Không có bước nào cần chạy - mọi thứ đã mới.")

    for item in runner.skipped:
        print(f"  [BỎ QUA  ] {item}")

    print("=" * 70)

    if arguments.check:
        # Mã thoát 1 khi còn việc phải làm, để dùng được trong script kiểm tra.
        raise SystemExit(1 if runner.done else 0)

    print("Bước 5 trong README (chạy web) là tiến trình chạy mãi, không đưa vào đây:")
    print("    python MaNguon\\api_server.py")
    print("hoặc bấm ThuMucKhoiChay\\2_Chay_Web.bat")


if __name__ == "__main__":
    main()
