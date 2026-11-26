/*
  Đường dẫn: Du_An_Hoc_May_Nang_Cao\Web\app.js
  Mục đích : Đọc window.WEB_DATA_META + window.WEB_DATA_REVIEWS (do
             MaNguon/export_web_data.py sinh ra) hoặc kết quả API, rồi vẽ dashboard
             lọc review hữu ích.
  Input    : window.WEB_DATA_META; window.WEB_DATA_REVIEWS nạp sau;
             phản hồi từ /api/predict và /api/analyze-file.
  Output   : nội dung hiển thị trên trang index.html.

  Vì sao dữ liệu tách hai file:
    data_meta.js nhỏ, nạp ngay để hiện số liệu và biểu đồ.
    data_reviews.js hơn 4 MB, chỉ nạp khi cần vẽ bảng.
    Cách nạp vẫn là thẻ <script> vì mở bằng double-click dùng giao thức file://,
    trình duyệt chặn fetch() ở giao thức này.

  Quy ước tên biến (theo MaNguon/config.py):
    - Tên đầy đủ, không viết tắt: probabilities, threshold, predictions...
    - SVG: Scalable Vector Graphics.
    - DOM: Document Object Model.
    - KPI: Key Performance Indicator.
    - CSV: Comma-Separated Values.
*/

"use strict";

// Không gian tên bắt buộc khi tạo phần tử SVG bằng JavaScript.
const SVG_NAMESPACE = "http://www.w3.org/2000/svg";

/* ============================================================
   Thông tin hiển thị của 5 nhóm
   ============================================================ */

// Thứ tự này phải khớp CATEGORY_ORDER trong MaNguon/config.py.
// Dùng let vì lúc khởi động sẽ thay bằng danh sách do Python xuất trong meta,
// tránh hai nơi lệch thứ tự khi bảo trì.
let CATEGORY_ORDER = [
  "genuine",
  "suspected_fake",
  "suspected_bot_boost",
  "low_content",
  "spam_duplicate"
];

// tone dùng cho CSS: good (xanh), bad (đỏ), warn (vàng), muted (xám).
// Không dùng icon trong thẻ nhóm: màu viền + huy hiệu chữ là tín hiệu chính.
const CATEGORY_INFO = {
  genuine: {
    label: "Hữu ích",
    tone: "good",
    description: "Người viết, đủ dài, không trùng lặp"
  },
  suspected_fake: {
    label: "Nghi giả",
    tone: "bad",
    description: "Model cho là văn bản máy sinh"
  },
  suspected_bot_boost: {
    label: "Nghi bot/boost",
    tone: "warn",
    description: "Máy sinh + 5 sao + nội dung ngắn"
  },
  low_content: {
    label: "Quá ngắn",
    tone: "muted",
    description: "Dưới 5 từ, không đủ thông tin"
  },
  spam_duplicate: {
    label: "Trùng lặp",
    tone: "muted",
    description: "Trùng khít một review phía trước"
  }
};

// Nhãn cơ sở và mẫu câu lý do do Python xuất trong data_meta.js.
// Vì sao để trống lúc đầu: nếu file meta cũ chưa có, trang vẫn chạy với
// giá trị mặc định thay vì báo lỗi.
let BASIS_LABELS = {
  model: "MODEL",
  rule: "LUẬT",
  "model+rule": "MODEL + LUẬT"
};
let REASON_TEMPLATES = {};

const FLAG_INFO = {
  low_content: "quá ngắn",
  duplicate: "trùng",
  has_link: "có link",
  five_star: "5 sao",
  model_fake: "model cho là giả",
  low_confidence: "không đáng tin",
  translation_borderline: "sát ngưỡng do dịch",
  translation_inconsistent: "dịch vòng lệch nghĩa"
};

/* ============================================================
   Trạng thái trang
   ============================================================ */

const state = {
  source: "demo",        // "demo" hoặc "upload"
  demoData: null,        // đã ghép window.WEB_DATA_META + window.WEB_DATA_REVIEWS
  uploadData: null,      // phản hồi /api/analyze-file
  uploadFileName: "",
  rows: [],              // dữ liệu đang hiển thị
  summary: null,         // số lượng theo nhóm và theo sao
  meta: null,            // thông tin chung của nguồn đang xem
  hasTrueLabel: false,   // chỉ dữ liệu demo mới có nhãn thật
  filter: "genuine",     // mặc định chỉ giữ review hữu ích
  star: "all",           // "all" hoặc "1".."5", gom theo Math.round(rating)
  query: "",             // tìm nội dung review, chuẩn hoá không dấu
  flag: null,            // lọc theo một cờ trong review.flags
  currentPage: 1,
  pageSize: 25,

  // Bảng CSV đang sửa trên web. Tách khỏi uploadData: sửa xong mới gửi API,
  // nên dữ liệu kết quả cũ không bị ghi đè khi người dùng chỉ đang gõ.
  edit: {
    loaded: false,
    fileName: "",
    headers: [],
    rows: [],
    hasBom: false,
    eol: "\n",
    page: 1,
    pageSize: 12
  }
};

// Reload mở trang ở trạng thái chờ hiện số: 5 thẻ nhóm và thanh phân bố 5 sao
// đứng yên ở 0. Chỉ khi bấm "Hiện lại dữ liệu" mới chạy delay + tăng số.
let revealPending = false;

// Trạng thái riêng của bảng demo: mở/đóng, toàn bộ review và bộ lọc. Tách khỏi
// state để không bị applyPayload() đặt lại mỗi lần chạy luồng huấn luyện.
const demoPreview = {
  open: false,
  reviews: [],
  query: "",
  star: "all",
  label: "all",
  category: "all"
};

/* ============================================================
   Chế độ sáng / tối
   ============================================================ */

// Khóa lưu trong localStorage. Vì sao lưu: người xem đã chọn nền tối thì
// lần sau mở trang không phải bấm lại.
const THEME_STORAGE_KEY = "fake-review-theme";

// Đọc màu từ CSS thay vì viết mã màu trong JS.
// Vì sao: biểu đồ là SVG tạo bằng JS nên màu đường/trục được ghi thẳng vào
// thuộc tính; nếu để mã màu cứng thì sang nền tối chữ và đường sẽ chìm vào nền.
function themeColor(name, fallback) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark"
    ? "dark"
    : "light";
}

// localStorage có thể bị chặn (chế độ riêng tư, cấu hình bảo mật), nên mọi
// truy cập đều nằm trong try: hỏng thì dùng mặc định, không làm sập trang.
function readStoredTheme() {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeTheme(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    return;
  }
}

function applyTheme(theme) {
  const isDark = theme === "dark";
  document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");

  const button = document.getElementById("theme-toggle");
  if (button) {
    // Nhãn ghi hành động sẽ xảy ra khi bấm, không ghi trạng thái hiện tại.
    button.setAttribute("aria-pressed", isDark ? "true" : "false");
    button.title = isDark ? "Chuyển sang nền sáng" : "Chuyển sang nền tối";
  }

  const icon = document.getElementById("theme-toggle-icon");
  if (icon) {
    icon.textContent = isDark ? "\u2600" : "\u263e";
  }

  const label = document.getElementById("theme-toggle-text");
  if (label) {
    label.textContent = isDark ? "Nền sáng" : "Nền tối";
  }
}

function switchTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  storeTheme(next);
  applyTheme(next);
}

function initTheme() {
  const stored = readStoredTheme();
  // Mặc định nền sáng: trang dùng để trình bày báo cáo trên máy chiếu.
  applyTheme(stored === "dark" ? "dark" : "light");

  const button = document.getElementById("theme-toggle");
  if (!button) {
    return;
  }

  button.addEventListener("click", switchTheme);
}

/* ============================================================
   Menu dọc bên trái
   ============================================================ */

const SIDEBAR_STORAGE_KEY = "fake-review-sidebar";

function isSidebarCollapsed() {
  return document.documentElement.getAttribute("data-sidebar") === "collapsed";
}

function syncSidebarToggle() {
  const button = document.getElementById("menu-toggle");
  if (!button) {
    return;
  }
  const collapsed = isSidebarCollapsed();
  const label = collapsed ? "Mở menu" : "Thu gọn menu";
  button.setAttribute("aria-expanded", collapsed ? "false" : "true");
  button.setAttribute("aria-label", label);
  button.title = label;

  const text = button.querySelector(".menu-toggle-text");
  if (text) {
    text.textContent = collapsed ? "Mở" : "Thu gọn";
  }
}

function storeSidebarState(collapsed) {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "collapsed" : "open");
  } catch {
    return;
  }
}

function initMenu() {
  const button = document.getElementById("menu-toggle");
  const settings = document.getElementById("menu-settings");
  if (!button) {
    return;
  }

  syncSidebarToggle();
  button.addEventListener("click", function () {
    const collapsed = !isSidebarCollapsed();
    document.documentElement.setAttribute("data-sidebar", collapsed ? "collapsed" : "open");
    storeSidebarState(collapsed);
    syncSidebarToggle();
  });

  if (settings) {
    settings.addEventListener("click", switchTheme);
  }
}

/* ============================================================
   Màn hình chờ (Gooey) và tuần tự xử lý
   ============================================================ */

// Thời gian giữ mỗi pha để màn hình chờ không chớp quá nhanh khi dữ liệu đã
// nằm trong bộ nhớ đệm. Đổi ở đây là đổi toàn bộ nhịp, không rải số khắp nơi.
const BOOT_PAUSE_MS = 320;

// Nhịp đổi câu mô tả khi chờ API. API trả về một lần nên đây chỉ là mô tả
// tiến trình đang diễn ra phía server, không phải phần trăm thật.
const UPLOAD_PHASE_MS = 3000;

// Giữ màn hình chờ thêm một nhịp sau khi API trả về để người xem kịp đọc
// kết quả cuối cùng của cả 4 bước, thay vì lớp phủ biến mất ngay.
const UPLOAD_RESULT_HOLD_MS = 1400;

// Số review xử lý mỗi lượt khi tổng hợp dữ liệu demo. Chia lô để trình duyệt
// còn vẽ được thanh tiến độ giữa các lô.
const DEMO_AGGREGATE_CHUNK = 500;

// Mỗi lượt cuộn tới đáy khung thì nạp thêm 100 dòng, đủ nhẹ để trình duyệt vẫn
// mượt khi bảng có hơn 6000 review.
const INFINITE_PAGE_SIZE = 100;

// Tín hiệu nội bộ để dừng luồng thinking khi bấm Huỷ. Dùng object riêng thay vì
// chuỗi để không nhầm với lỗi thật nào đó trong quá trình xử lý.
const CANCEL_SENTINEL = { cancelled: true };

const loaderState = {
  screen: null,
  title: null,
  detail: null,
  log: null,
  timer: null,
  startedAt: 0,
  timerId: 0,
  limitSeconds: 0,
  cancelled: false,
  cardsVisible: false,
  // Lưu kết quả từng bước để sau khi chạy xong dựng bảng chi tiết.
  steps: []
};

function loaderPart(key, id) {
  if (!loaderState[key]) {
    loaderState[key] = document.getElementById(id);
  }
  return loaderState[key];
}

/* ============================================================
   loading_skeleton + đếm tăng tốc cho ô số
   ============================================================ */

// Chỉ các nút chứa số mới nằm ở đây. Tiêu đề, mô tả, chữ "review" hay dấu "%"
// đều nằm ngoài danh sách nên không bị làm mờ trong lúc thinking.
const SKELETON_TARGETS = [
  { key: "preview", selector: "#preview-count .preview-count-number" },
  { key: "useful", selector: ".useful-pill-value" },
  { key: "category", selector: ".category-count" },
  { key: "percent", selector: ".category-percent" },
  { key: "star", selector: ".star-meter-count" }
];

const NUMBER_RUSH_MS = 950;
const NUMBER_RUSH_STAGGER_MS = 55;

function forEachSkeletonTarget(callback) {
  for (let t = 0; t < SKELETON_TARGETS.length; t++) {
    const target = SKELETON_TARGETS[t];
    const nodes = document.querySelectorAll(target.selector);
    for (let i = 0; i < nodes.length; i++) {
      callback(nodes[i], target.key + "-" + i);
    }
  }
}

// Lấy số đang hiển thị trước khi bật skeleton. Nếu số đó đã bằng số cuối (ví
// dụ bấm chạy lại) thì deriveSpeedStart() sẽ tạo một mốc thấp hơn để vẫn có
// đoạn tăng tốc nhìn được.
function captureNumberStarts() {
  const starts = {};
  forEachSkeletonTarget(function (element, key) {
    starts[key] = element.textContent.trim();
  });
  return starts;
}

// Tách một chuỗi thành phần chữ + phần số + phần sau số. Ví dụ "6.062 review"
// thành before="", digits="6062", mask="\0.\0\0\0", after=" review".
function numericParts(text) {
  const value = String(text === undefined || text === null ? "" : text);
  const match = value.match(/\d[\d.,]*/);
  if (!match) {
    return null;
  }
  const numberText = match[0];
  return {
    before: value.slice(0, match.index),
    after: value.slice(match.index + numberText.length),
    digits: numberText.replace(/\D/g, ""),
    mask: numberText.replace(/\d/g, "\u0000")
  };
}

function renderWithDigits(parts, digits) {
  let cursor = 0;
  const number = parts.mask.replace(/\u0000/g, function () {
    return digits[cursor++] || "0";
  });
  return parts.before + number + parts.after;
}

// Tạo điểm xuất phát gần số cuối: giữ nguyên phần đầu, chỉ hạ 2 chữ số cuối
// (hoặc 3 nếu 2 chữ số cuối toàn số 0). Đây là mốc để phần đuôi tăng tốc.
function deriveSpeedStart(finalText) {
  const parts = numericParts(finalText);
  if (!parts || !parts.digits) {
    return finalText;
  }

  const digits = parts.digits;
  if (digits.length <= 1) {
    return renderWithDigits(parts, "0");
  }

  let suffixLength = Math.min(2, digits.length);
  let prefixLength = digits.length - suffixLength;
  let suffixValue = parseInt(digits.slice(prefixLength), 10);
  if (suffixValue <= 1 && digits.length > suffixLength) {
    suffixLength = Math.min(3, digits.length);
    prefixLength = digits.length - suffixLength;
    suffixValue = parseInt(digits.slice(prefixLength), 10);
  }
  if (!Number.isFinite(suffixValue) || suffixValue <= 1) {
    return renderWithDigits(parts, "0".repeat(digits.length));
  }

  const drop = Math.max(1, Math.floor(suffixValue * 0.25));
  const startSuffix = Math.max(0, suffixValue - drop);
  const startDigits =
    digits.slice(0, prefixLength) + String(startSuffix).padStart(suffixLength, "0");
  return renderWithDigits(parts, startDigits);
}

// Hàm dùng lại cho mọi luồng có waiting: bật/tắt skeleton chỉ trên ô số.
function loading_skeleton(active, options) {
  const settings = options || {};
  const starts = settings.starts || {};

  forEachSkeletonTarget(function (element, key) {
    if (active) {
      const finalText = element.textContent.trim();
      if (!finalText) {
        return;
      }
      const captured = starts[key];
      const fromText = captured && captured !== finalText
        ? captured
        : deriveSpeedStart(finalText);
      element.dataset.skeletonFrom = fromText;
      element.dataset.skeletonFinal = finalText;
      element.classList.add("is-loading-skeleton");
      element.setAttribute("aria-busy", "true");
      return;
    }

    element.classList.remove("is-loading-skeleton");
    element.removeAttribute("aria-busy");
    delete element.dataset.skeletonFrom;
    delete element.dataset.skeletonFinal;
  });
}

// Đọc kế hoạch trước khi applyPayload() dựng lại các ô số: các nút cũ sẽ bị
// thay thế, nên phải mang theo mốc bắt đầu theo từng key.
function collectSkeletonRushPlan() {
  const plan = {};
  forEachSkeletonTarget(function (element, key) {
    if (element.dataset.skeletonFrom) {
      plan[key] = {
        from: element.dataset.skeletonFrom,
        final: element.dataset.skeletonFinal || element.textContent.trim()
      };
    }
  });
  return plan;
}

// Chỉ animate thanh progress bên trong 5 thẻ nhóm (Hữu ích, Nghi giả, Nghi bot,
// Quá ngắn, Trùng lặp). Các ô số khác như "review" hay 5 sao không có thanh riêng.
function reportRushProgress(element, value) {
  const card = element.closest ? element.closest(".category-card") : null;
  if (!card) {
    return;
  }
  const fill = card.querySelector(".category-bar-fill");
  if (!fill) {
    return;
  }
  const finalWidth = parseFloat(fill.dataset.finalWidth || fill.style.width || "0");
  if (!Number.isFinite(finalWidth)) {
    return;
  }
  const clamped = Math.max(0, Math.min(1, value));
  // Mỗi thẻ có 2 ô số (số lượng + %) cùng đẩy một thanh. Chỉ nhận giá trị lớn
  // hơn mốc cũ để thanh không tụt lại khi một ô chạy xong trước ô kia.
  const previous = parseFloat(fill.dataset.rushProgress || "0");
  const next = Number.isFinite(previous) ? Math.max(previous, clamped) : clamped;
  fill.dataset.rushProgress = String(next);
  fill.style.width = (finalWidth * next).toFixed(2) + "%";
}

// Chỉ animate phần chữ số khác nhau. 3030 -> 3040 có prefix "30" nên chỉ chạy
// "30" -> "40"; 0 -> 3040 không có prefix chung nên chạy cả bốn chữ số.
function animateNumberRush(element, fromText, finalText, delay) {
  if (!element) {
    return;
  }

  const target = numericParts(finalText);
  const source = numericParts(fromText);
  if (!target || !source || !target.digits) {
    element.textContent = finalText;
    return;
  }

  if (element.rushFrameId) {
    window.cancelAnimationFrame(element.rushFrameId);
    element.rushFrameId = 0;
  }

  const length = target.digits.length;
  const fromDigits = source.digits.slice(-length).padStart(length, "0");
  const toDigits = target.digits;
  let common = 0;
  while (common < length && fromDigits[common] === toDigits[common]) {
    common++;
  }

  const prefix = toDigits.slice(0, common);
  const suffixLength = length - common;
  const fromValue = suffixLength ? parseInt(fromDigits.slice(common), 10) : 0;
  const toValue = suffixLength ? parseInt(toDigits.slice(common), 10) : 0;

  function paint(digits) {
    element.textContent = renderWithDigits(target, digits);
  }

  const reduceMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduceMotion || suffixLength === 0 || !Number.isFinite(fromValue) ||
      !Number.isFinite(toValue) || fromValue === toValue) {
    paint(toDigits);
    // Vẫn đưa thanh của 5 thẻ nhóm về mốc cuối: nếu không, lúc reload đặt
    // width = 0% ở trên sẽ bị kẹt lại khi người xem tắt hiệu ứng chuyển động.
    reportRushProgress(element, 1);
    return;
  }

  element.classList.add("is-number-rushing");
  const startAt = performance.now() + (delay || 0);

  function frame(now) {
    if (now < startAt) {
      element.rushFrameId = window.requestAnimationFrame(frame);
      return;
    }

    const elapsed = now - startAt;
    const time = Math.min(1, elapsed / NUMBER_RUSH_MS);
    // Gia tốc kiểu ô tô: đầu chậm, cuối nhanh dần tới số đích.
    const eased = time * time;
    const value = Math.round(fromValue + (toValue - fromValue) * eased);
    paint(prefix + String(value).padStart(suffixLength, "0"));
    reportRushProgress(element, eased);

    if (time < 1) {
      element.rushFrameId = window.requestAnimationFrame(frame);
      return;
    }

    element.rushFrameId = 0;
    reportRushProgress(element, 1);
    paint(toDigits);
    window.setTimeout(function () {
      if (element.rushFrameId === 0) {
        element.classList.remove("is-number-rushing");
        reportRushProgress(element, 1);
      }
    }, 260);
  }

  element.rushFrameId = window.requestAnimationFrame(frame);
}

// Nhịp xuất hiện khi reload: thẻ kết quả phân loại hiện trước (0ms); 5 thẻ nhóm
// lần lượt 0.15 / 0.25 / 0.3 / 0.375 / 0.45s; các thẻ mẹ còn lại nằm trong 0.75-0.85s.
const CARD_ENTER_MS = 420;
const CATEGORY_DELAY_MS = {
  genuine: 150,
  suspected_fake: 250,
  suspected_bot_boost: 350,
  low_content: 450,
  spam_duplicate: 550
};
const OTHER_CARD_DELAY_START_MS = 750;
const OTHER_CARD_DELAY_STEP_MS = 50;
const OTHER_CARD_DELAY_MAX_MS = 850;

function reducedMotionEnabled() {
  return Boolean(window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}

function entranceDelayFor(element, otherCards) {
  if (element.classList.contains("category-card")) {
    const configured = CATEGORY_DELAY_MS[element.dataset.category];
    return typeof configured === "number" ? configured : 150;
  }
  if (element.id === "summary-card") {
    return 0;
  }
  return Math.min(OTHER_CARD_DELAY_MAX_MS,
    OTHER_CARD_DELAY_START_MS + otherCards.indexOf(element) * OTHER_CARD_DELAY_STEP_MS);
}

// Dựng hiệu ứng xuất hiện lần lượt cho các thẻ đang hiện, kể cả 5 thẻ nhóm bên
// trong thẻ kết quả. Thẻ đã chạy rồi (dataset.entered) không chạy lại lần hai.
function playCardEntrance() {
  if (reducedMotionEnabled()) {
    return;
  }
  const parentCards = Array.prototype.slice.call(
    document.querySelectorAll("main > .card")
  );
  const otherCards = parentCards.filter(function (card) {
    return card.id !== "summary-card";
  });
  const categoryCards = Array.prototype.slice.call(
    document.querySelectorAll("main .category-card")
  );
  const elements = parentCards.concat(categoryCards);

  for (let i = 0; i < elements.length; i++) {
    const element = elements[i];
    if (element.dataset.entered === "1" || element.closest("[hidden]")) {
      continue;
    }
    const delay = entranceDelayFor(element, otherCards);
    element.dataset.entered = "1";
    element.style.animationDelay = delay + "ms";
    element.classList.add("is-entering");

    let finished = false;
    let fallbackId = 0;
    function onEnd(event) {
      if (event.target !== element || event.animationName !== "card-enter") {
        return;
      }
      finish();
    }
    function finish() {
      if (finished) {
        return;
      }
      finished = true;
      element.removeEventListener("animationend", onEnd);
      window.clearTimeout(fallbackId);
      element.classList.remove("is-entering");
      element.style.removeProperty("animation-delay");
    }
    element.addEventListener("animationend", onEnd);
    // Phòng khi animation không chạy (thẻ bị ẩn ngay sau đó): vẫn dọn class.
    fallbackId = window.setTimeout(finish, delay + CARD_ENTER_MS + 200);
  }
}

function applyRushPlan(plan, options) {
  const settings = options || {};
  const waitForEntrance = settings.waitForEntrance === true && !reducedMotionEnabled();
  let order = 0;
  forEachSkeletonTarget(function (element, key) {
    const entry = plan[key];
    if (!entry) {
      return;
    }

    let started = false;
    function start() {
      if (started) {
        return;
      }
      started = true;
      // Đặt mốc bắt đầu trước, không gán số đích ở đây: gán đích rồi mới gọi
      // animateNumberRush() sẽ có một khung hình nhảy lên đích rụt về 0.
      if (element.textContent.trim() !== entry.from) {
        element.textContent = entry.from;
      }
      animateNumberRush(element, entry.from, entry.final, order * NUMBER_RUSH_STAGGER_MS);
    }

    // Khi reload, chỉ bật nhảy múa sau khi thẻ chứa ô số đó hiện xong (opacity 1).
    // Với số trong 5 nhóm thì đợi chính thẻ nhóm, không đợi thẻ mẹ bao ngoài.
    const card = waitForEntrance && element.closest
      ? (element.closest(".category-card") || element.closest(".card"))
      : null;
    if (card && card.classList.contains("is-entering")) {
      let cleanup = null;
      function onEnd(event) {
        if (event.target !== card || event.animationName !== "card-enter") {
          return;
        }
        if (cleanup) {
          cleanup();
        }
        start();
      }
      card.addEventListener("animationend", onEnd);
      const timeoutId = window.setTimeout(function () {
        if (cleanup) {
          cleanup();
        }
        start();
      }, OTHER_CARD_DELAY_MAX_MS + CARD_ENTER_MS + 500);
      cleanup = function () {
        card.removeEventListener("animationend", onEnd);
        window.clearTimeout(timeoutId);
      };
    } else {
      start();
    }
    order++;
  });
}

/* ============================================================
   Hiện lại dữ liệu cũ sau khi reload
   ============================================================ */

// Mốc 0 luôn là một chữ số, giữ lại phần chữ quanh số: "6.062" -> "0",
// "12.3%" -> "0%". Không đệm 0000 nên trang load nhìn gọn và đúng ý.
function singleZeroText(finalText) {
  const parts = numericParts(finalText);
  if (!parts || !parts.digits) {
    return finalText;
  }
  return parts.before + "0" + parts.after;
}

function setRevealButtonState(pending) {
  const button = document.getElementById("reveal-data-button");
  if (!button) {
    return;
  }
  button.disabled = !pending;
  button.textContent = pending ? "Hiện lại dữ liệu" : "Đã hiện dữ liệu";
}

// Reload chỉ nạp dữ liệu và dựng bảng ở dạng 0. Không playCardEntrance(), không
// applyRushPlan(): mọi nhịp delay được dành cho lúc bấm nút hiện lại.
function preparePendingReveal() {
  const demo = state.demoData;
  if (!demo) {
    return;
  }
  revealPending = true;
  applyPayload(demo, "demo");
  setPayloadVisibility(true);
  setRevealButtonState(true);
}

// Nút "Hiện lại dữ liệu": chạy đúng nhịp cũ – thẻ hiện theo delay riêng, số đợi
// thẻ của nó hiện xong rồi tăng, thanh 5 thẻ nhóm ăn theo tiến độ đó.
function revealPendingData() {
  if (!revealPending) {
    return;
  }
  revealPending = false;
  setRevealButtonState(false);

  const plan = {};
  forEachSkeletonTarget(function (element, key) {
    const finalText = element.dataset.finalText || "";
    if (!finalText) {
      return;
    }
    plan[key] = { from: singleZeroText(finalText), final: finalText };
  });

  playCardEntrance();
  applyRushPlan(plan, { waitForEntrance: true });
  revealStarMeters();
}

// Thanh phân bố 5 sao có sẵn transition width. Chỉ cần đẩy về mốc đích sau khi
// thẻ chứa nó hiện xong, cộng thêm một nhịp nhỏ theo từng cột để không đồng loạt.
function revealStarMeters() {
  const starCard = document.getElementById("star-card");
  const cardDelay = starCard
    ? parseFloat(starCard.style.animationDelay || "0")
    : 0;
  const baseDelay = Number.isFinite(cardDelay) ? cardDelay : 0;
  const fills = document.querySelectorAll(".star-meter-fill[data-final-width]");
  for (let i = 0; i < fills.length; i++) {
    const fill = fills[i];
    fill.style.transitionDelay = (baseDelay + (i % 10) * 35) + "ms";
    fill.style.width = fill.dataset.finalWidth;
  }
}

// pause() vừa là nhịp nghỉ giữa các bước, vừa là điểm dừng khi bấm Huỷ. Cứ
// khoảng 50ms lại kiểm tra cờ, nên luồng dừng gần như ngay lập tức.
function pause(milliseconds) {
  return new Promise(function (resolve, reject) {
    if (loaderState.cancelled) {
      reject(CANCEL_SENTINEL);
      return;
    }
    const startedAt = Date.now();
    function tick() {
      if (loaderState.cancelled) {
        reject(CANCEL_SENTINEL);
        return;
      }
      const elapsed = Date.now() - startedAt;
      if (elapsed >= milliseconds) {
        resolve();
        return;
      }
      window.setTimeout(tick, Math.min(50, milliseconds - elapsed));
    }
    window.setTimeout(tick, Math.min(50, milliseconds));
  });
}

function setLoaderText(title, detail) {
  const titleElement = loaderPart("title", "loader-title");
  const detailElement = loaderPart("detail", "loader-detail");
  if (titleElement && title !== null) {
    titleElement.textContent = title;
  }
  if (detailElement && detail !== null) {
    detailElement.textContent = detail;
  }
}

function resetLoaderLog() {
  const list = loaderPart("log", "loader-log");
  if (list) {
    list.replaceChildren();
  }
  loaderState.steps = [];
}

// Mỗi dòng là kết quả CUỐI CÙNG của một bước đã xong. Chỉ gọi sau khi bước đó
// thật sự hoàn tất, không gọi trước để tránh hiện kết quả chưa có.
function completeLoaderStep(step, result) {
  const list = loaderPart("log", "loader-log");
  if (!list) {
    return;
  }

  const item = document.createElement("li");
  item.className = "loader-log-item";

  const check = document.createElement("span");
  check.className = "loader-log-check";
  check.setAttribute("aria-hidden", "true");
  check.textContent = "✓";

  const body = document.createElement("span");
  const stepNode = document.createElement("span");
  stepNode.className = "loader-log-step";
  stepNode.textContent = step;
  const resultNode = document.createElement("span");
  resultNode.className = "loader-log-result";
  resultNode.textContent = result;

  body.appendChild(stepNode);
  body.appendChild(resultNode);
  item.appendChild(check);
  item.appendChild(body);
  list.appendChild(item);
  list.scrollTop = list.scrollHeight;

  loaderState.steps.push({ name: step, result: result });
}

// Tóm tắt 5 nhóm trên một dòng, dùng chung cho demo và file tải lên.
function loaderCategorySummary(categories) {
  const parts = [];
  for (let i = 0; i < CATEGORY_ORDER.length; i++) {
    const categoryId = CATEGORY_ORDER[i];
    parts.push(
      categoryInfo(categoryId).label + " " +
      countText(categories[categoryId] || 0)
    );
  }
  return parts.join(" · ");
}

// Khoảng xác suất thực tế của lượt upload. Hiện khoảng thay vì một con số
// trung bình để người xem thấy dữ liệu nằm sát ngưỡng ra sao.
function loaderProbabilityRange(rows) {
  let minimum = Infinity;
  let maximum = -Infinity;
  for (let i = 0; i < rows.length; i++) {
    const probability = Number(rows[i].prob_fake);
    if (!Number.isFinite(probability)) {
      continue;
    }
    minimum = Math.min(minimum, probability);
    maximum = Math.max(maximum, probability);
  }
  if (!Number.isFinite(minimum)) {
    return "";
  }
  return percentText(minimum) + "–" + percentText(maximum);
}

function renderLoaderTimer() {
  const timer = loaderPart("timer", "loader-timer");
  if (!timer) {
    return;
  }
  if (!loaderState.limitSeconds) {
    timer.textContent = "";
    return;
  }
  const elapsed = Math.floor((Date.now() - loaderState.startedAt) / 1000);
  timer.textContent =
    "Đã chờ " + elapsed + " giây · giới hạn dịch " +
    loaderState.limitSeconds + " giây";
}

function showLoader(title, detail, options) {
  const settings = options || {};
  const screen = loaderPart("screen", "loader-screen");
  if (!screen) {
    return;
  }

  screen.classList.remove("is-hidden");
  screen.classList.remove("is-result");
  const resultPanel = document.getElementById("result-panel");
  if (resultPanel) {
    resultPanel.hidden = true;
  }
  // Sau lần trước, nút đóng result panel đã ẩn khối thinking. Phải hiện lại
  // khi bấm "Chạy lại", nếu không lớp phủ sẽ trống.
  const thinking = document.getElementById("loader-panel");
  if (thinking) {
    thinking.hidden = false;
  }
  // Khung nút chung: thinking chỉ hiện Huỷ, result chỉ hiện Đóng/Chạy lại.
  const cancelButton = document.getElementById("loader-cancel");
  if (cancelButton) {
    cancelButton.hidden = false;
  }
  const resultActions = document.getElementById("result-actions");
  if (resultActions) {
    resultActions.hidden = true;
  }
  const resultNote = document.getElementById("result-note");
  if (resultNote) {
    resultNote.textContent = "";
  }
  // Chạy một luồng mới thì trạng thái chờ hiện số ở lần reload trước không còn
  // nữa: số sẽ do luồng chạy cập nhật, nút "Hiện lại dữ liệu" cũng vô hiệu hoá.
  revealPending = false;
  setRevealButtonState(false);

  // Mỗi lần chạy mới (kể cả luồng upload) bắt đầu với cờ huỷ sạch. Nhớ luôn
  // trạng thái các thẻ số để nút Huỷ đưa trang về đúng chỗ cũ.
  loaderState.cancelled = false;
  const summaryCard = document.getElementById("summary-card");
  loaderState.cardsVisible = Boolean(summaryCard && !summaryCard.hidden);
  document.body.classList.add("is-processing");
  resetLoaderLog();
  setLoaderText(title, detail);

  loaderState.limitSeconds = settings.limitSeconds || 0;
  loaderState.startedAt = Date.now();
  window.clearInterval(loaderState.timerId);
  renderLoaderTimer();
  loaderState.timerId = window.setInterval(renderLoaderTimer, 500);
}

function hideLoader() {
  const screen = loaderPart("screen", "loader-screen");
  if (!screen) {
    return;
  }
  // Đảm bảo không ô số nào bị kẹt ở trạng thái skeleton nếu luồng bị ngắt.
  loading_skeleton(false);
  window.clearInterval(loaderState.timerId);
  loaderState.timerId = 0;
  screen.classList.add("is-hidden");
  screen.classList.remove("is-result");
  const resultPanel = document.getElementById("result-panel");
  if (resultPanel) {
    resultPanel.hidden = true;
  }
  document.body.classList.remove("is-processing");
  const timer = loaderPart("timer", "loader-timer");
  if (timer) {
    timer.textContent = "";
  }
}

// Đếm lại nhóm/số sao ngay trong trình duyệt. Đây là việc thật, dùng để vừa
// hiện tiến độ vừa đối chiếu với con số Python đã xuất trong data_meta.js.
function aggregateDemoReviews(reviews, onProgress) {
  return new Promise(function (resolve, reject) {
    const totals = { total: 0, useful: 0, categories: {}, stars: {} };
    let index = 0;

    function step() {
      if (loaderState.cancelled) {
        reject(CANCEL_SENTINEL);
        return;
      }
      const end = Math.min(index + DEMO_AGGREGATE_CHUNK, reviews.length);
      for (; index < end; index++) {
        const review = reviews[index];
        totals.total += 1;
        if (review.is_useful) {
          totals.useful += 1;
        }
        totals.categories[review.category] =
          (totals.categories[review.category] || 0) + 1;

        const star = Math.round(Number(review.rating) || 0);
        if (star >= 1 && star <= 5) {
          totals.stars[star] = (totals.stars[star] || 0) + 1;
        }
      }

      if (onProgress) {
        onProgress(reviews.length > 0 ? index / reviews.length : 1);
      }

      if (index < reviews.length) {
        // Nhường một nhịp cho trình duyệt vẽ thanh tiến độ.
        window.setTimeout(step, 0);
      } else {
        resolve(totals);
      }
    }

    step();
  });
}

// So con số vừa đếm với summary do Python xuất. Chỉ khi khớp mới dám hiện
// "đối chiếu khớp"; lệch thì im lặng dùng con số gốc.
function demoSummaryMatches(aggregate, summary) {
  if (!summary || aggregate.total !== summary.total) {
    return false;
  }
  if (aggregate.useful !== summary.useful_count) {
    return false;
  }

  for (let i = 0; i < CATEGORY_ORDER.length; i++) {
    const categoryId = CATEGORY_ORDER[i];
    if ((aggregate.categories[categoryId] || 0) !== (summary.categories[categoryId] || 0)) {
      return false;
    }
  }
  return true;
}

// Chạy tuần tự: khởi động -> nạp dữ liệu -> trích đặc trưng -> dự đoán ->
// đánh giá -> tổng hợp. Khác bản cũ: không tự chạy lúc mở trang, và khi xong
// giữ lại lớp phủ để người xem mở từng giai đoạn bằng bảng và biểu đồ.
// Bọc luồng thật: nút Huỷ chỉ cần ném tín hiệu CANCEL_SENTINEL, còn lỗi thật
// vẫn nổi lên bình thường để không che giấu sự cố.
async function runProcessingSequence() {
  if (document.body.classList.contains("is-processing")) {
    return;
  }
  try {
    await runProcessingFlow();
  } catch (error) {
    if (error !== CANCEL_SENTINEL) {
      throw error;
    }
  }
}

async function runProcessingFlow() {
  const demo = state.demoData;
  if (!demo) {
    return;
  }

  const summary = demo.summary;
  const meta = demo.meta;
  const technical = demo.technical;
  const threshold = meta.threshold;
  const dataset = technical && technical.metrics && technical.metrics.dataset
    ? technical.metrics.dataset
    : {
        rows_train: 0,
        rows_val: meta.rows_val || 0,
        rows_test: meta.rows_test || 0,
        n_features: 0
      };

  state.source = "demo";
  document.getElementById("tab-demo").classList.add("is-active");
  document.getElementById("tab-upload").classList.remove("is-active");
  document.getElementById("upload-card").hidden = true;
  updateSourceNote();
  renderBadges();

  // Lấy mốc số trước khi dựng lại bảng. Nút "Chạy lại" sẽ có sẵn số của lần
  // trước; với lượt đầu thì deriveSpeedStart() tự tạo mốc gần số cuối.
  const numberStarts = captureNumberStarts();

  showLoader(
    "Khởi động mô hình",
    "Nạp vectorizer TF-IDF và hệ số Logistic Regression..."
  );

  const reviews = await ensureDemoReviews();
  if (Array.isArray(reviews) && reviews.length > 0) {
    demo.reviews = reviews;
    applyPayload(demo, "demo");
    setPayloadVisibility(true);
    updateSourceNote();
    renderBadges();
    loading_skeleton(true, { starts: numberStarts });
  } else {
    setPayloadVisibility(false);
  }

  await pause(BOOT_PAUSE_MS);
  completeLoaderStep(
    "Khởi động mô hình",
    "Logistic Regression + TF-IDF · ngưỡng " + threshold.toFixed(2)
  );

  setLoaderText(
    "Nạp dữ liệu huấn luyện",
    "Đọc " + countText(dataset.rows_train) + " train / " +
    countText(dataset.rows_val) + " val / " +
    countText(dataset.rows_test) + " test..."
  );
  await pause(BOOT_PAUSE_MS);

  if (!Array.isArray(reviews) || reviews.length === 0) {
    completeLoaderStep("Nạp dữ liệu huấn luyện", "Không đọc được data_reviews.js");
    setLoaderText("Dừng", "Hãy chạy python MaNguon\\export_web_data.py rồi tải lại trang.");
      showResultPanel();
    return;
  }

  completeLoaderStep(
    "Nạp dữ liệu huấn luyện",
    countText(dataset.rows_train) + " train · " +
    countText(dataset.rows_val) + " val · " +
    countText(dataset.rows_test) + " test"
  );

  setLoaderText(
    "Trích đặc trưng TF-IDF",
    "Chuẩn hoá chữ và đếm token trên từng review..."
  );
  const aggregate = await aggregateDemoReviews(reviews);
  await pause(BOOT_PAUSE_MS);
  completeLoaderStep(
    "Trích đặc trưng TF-IDF",
    countText(dataset.n_features) + " đặc trưng · " +
    countText(aggregate.total) + " review"
  );

  setLoaderText(
    "Dự đoán xác suất",
    "Áp ngưỡng " + threshold.toFixed(2) + " và xếp nhóm cho từng review..."
  );
  await pause(BOOT_PAUSE_MS);
  completeLoaderStep(
    "Dự đoán xác suất",
    "Ngưỡng " + threshold.toFixed(2) + " · " +
    loaderCategorySummary(aggregate.categories)
  );

  setLoaderText(
    "Đánh giá trên tập test",
    "Tính F1, ma trận nhầm và độ tin cậy của xác suất..."
  );
  await pause(BOOT_PAUSE_MS);
  const testMetrics = technical.metrics.test;
  completeLoaderStep(
    "Đánh giá trên tập test",
    "F1 " + percentText(testMetrics.f1) +
    " · accuracy " + percentText(testMetrics.accuracy)
  );

  setLoaderText(
    "Tổng hợp báo cáo",
    "Dựng bảng preview và biểu đồ cho từng giai đoạn..."
  );
  await pause(BOOT_PAUSE_MS);
  completeLoaderStep(
    "Tổng hợp báo cáo",
    "5 nhóm · bảng 5 sao · " + countText(aggregate.total) + " review"
  );

  let finalDetail;
  if (demoSummaryMatches(aggregate, summary)) {
    finalDetail =
      "Đối chiếu khớp: " + countText(aggregate.useful) +
      " review hữu ích trên " + countText(aggregate.total) + " review.";
  } else {
    finalDetail = "Đã xử lý " + countText(aggregate.total) + " review.";
  }
  setLoaderText("Hoàn tất", finalDetail);
  completeLoaderStep("Hoàn tất", finalDetail);
  await pause(UPLOAD_RESULT_HOLD_MS);
  showResultPanel();
}

/* ============================================================
   Bảng kết quả sau khi chạy xong
   ============================================================ */

let activeResultStage = 0;

function resultBlock(title, hintText) {
  const block = createDiv("result-block");
  const heading = document.createElement("h3");
  heading.textContent = title;
  block.appendChild(heading);
  if (hintText) {
    block.appendChild(createDiv("hint", hintText));
  }
  return block;
}

function shortText(text, maxLength) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (value.length <= maxLength) {
    return value;
  }
  return value.slice(0, maxLength) + "…";
}

function makeResultTable(headers, rows, limit) {
  const wrap = createDiv("result-table-wrap");
  const table = document.createElement("table");
  table.className = "result-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (let i = 0; i < headers.length; i++) {
    const cell = document.createElement("th");
    cell.textContent = headers[i];
    headRow.appendChild(cell);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  const rowLimit = limit || rows.length;
  for (let i = 0; i < Math.min(rows.length, rowLimit); i++) {
    const row = document.createElement("tr");
    for (let j = 0; j < headers.length; j++) {
      const cell = document.createElement("td");
      cell.textContent = String(rows[i][j] === undefined || rows[i][j] === null
        ? "" : rows[i][j]);
      row.appendChild(cell);
    }
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

/* ============================================================
   Bảng nạp dần khi cuộn + tìm kiếm không dấu
   ============================================================ */

// Chuẩn hoá để tìm cả "nha binh" lẫn "nhà bình". map lưu vị trí của từng ký tự
// đã gập lại trong chuỗi gốc, nên khi tô vàng vẫn trúng đúng chữ có dấu.
function foldForSearch(value) {
  const source = String(value === undefined || value === null ? "" : value);
  let folded = "";
  const map = [];
  for (let i = 0; i < source.length; i++) {
    const char = source.charAt(i);
    const decomposed = char.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    const base = decomposed === "đ" ? "d" : decomposed;
    for (let j = 0; j < base.length; j++) {
      folded += base.charAt(j);
      map.push(i);
    }
  }
  return { text: folded, map: map };
}

function appendHighlightedText(cell, value, query) {
  const source = String(value === undefined || value === null ? "" : value);
  const needle = query ? foldForSearch(query).text : "";
  if (!needle) {
    cell.textContent = source;
    return;
  }

  const folded = foldForSearch(source);
  let cursor = 0;
  let found = folded.text.indexOf(needle);
  if (found === -1) {
    cell.textContent = source;
    return;
  }

  while (found !== -1) {
    const start = folded.map[found];
    const end = folded.map[found + needle.length - 1] + 1;
    if (start > cursor) {
      cell.appendChild(document.createTextNode(source.slice(cursor, start)));
    }
    const mark = document.createElement("mark");
    mark.textContent = source.slice(start, end);
    cell.appendChild(mark);
    cursor = end;
    found = folded.text.indexOf(needle, found + needle.length);
  }
  if (cursor < source.length) {
    cell.appendChild(document.createTextNode(source.slice(cursor)));
  }
}

// Gắn nạp dần vào một tbody có sẵn. Gọi lại khi đổi bộ lọc sẽ thay controller
// cũ trên cùng khung cuộn, nên không bao giờ chồng nhiều listener.scroll.
function bindInfiniteTable(body, scrollHost, options) {
  const settings = options || {};
  const rows = Array.isArray(settings.rows) ? settings.rows : [];
  const query = settings.query || "";
  const status = settings.status || null;
  const totalText = settings.totalText || countText(rows.length) + " dòng";

  if (scrollHost._infiniteController) {
    scrollHost.removeEventListener("scroll", scrollHost._infiniteController.onScroll);
  }

  let rendered = 0;

  function updateStatus() {
    if (!status) {
      return;
    }
    if (rows.length === 0) {
      status.textContent = settings.emptyText || "Không có dòng nào khớp bộ lọc.";
    } else if (rendered >= rows.length) {
      status.textContent = "Đã hiện toàn bộ " + countText(rows.length) +
        " / " + totalText + ".";
    } else {
      status.textContent = "Đang hiện " + countText(rendered) + " / " + totalText +
        " · cuộn xuống để nạp thêm.";
    }
  }

  function appendBatch() {
    if (rendered >= rows.length) {
      updateStatus();
      return;
    }
    const end = Math.min(rendered + INFINITE_PAGE_SIZE, rows.length);
    const fragment = document.createDocumentFragment();
    for (let i = rendered; i < end; i++) {
      const rowNode = document.createElement("tr");
      const values = rows[i];
      for (let j = 0; j < values.length; j++) {
        const cell = document.createElement("td");
        appendHighlightedText(cell, values[j], query);
        rowNode.appendChild(cell);
      }
      fragment.appendChild(rowNode);
    }
    body.appendChild(fragment);
    rendered = end;
    updateStatus();
  }

  function onScroll() {
    const remaining = scrollHost.scrollHeight - scrollHost.scrollTop - scrollHost.clientHeight;
    if (remaining <= 48) {
      appendBatch();
    }
  }

  body.replaceChildren();
  scrollHost.addEventListener("scroll", onScroll);
  scrollHost._infiniteController = { onScroll: onScroll };
  appendBatch();

  // Nếu 100 dòng đầu chưa đủ đầy khung thì nạp thêm vài lô để thanh cuộn xuất hiện.
  let guard = 0;
  while (rendered < rows.length &&
         scrollHost.scrollHeight <= scrollHost.clientHeight + 8 &&
         guard < 3) {
    appendBatch();
    guard++;
  }
  scrollHost.scrollTop = 0;
}

// Dùng cho hai bảng preview trong result panel: tạo khung giống makeResultTable
// rồi gắn cơ chế nạp dần vào toàn bộ dòng thay vì chỉ mười dòng đầu.
function makeInfiniteResultTable(headers, rows, options) {
  const settings = options || {};
  const wrap = makeResultTable(headers, [], 0);
  wrap.classList.add("infinite-scroll-wrap");
  const body = wrap.querySelector("tbody");
  const status = createDiv("hint infinite-status", "");
  wrap.appendChild(status);
  if (body) {
    bindInfiniteTable(body, wrap, {
      rows: rows,
      query: settings.query || "",
      status: status,
      totalText: countText(rows.length) + " review"
    });
  }
  return wrap;
}

function labelText(value) {
  const demo = state.demoData;
  const threshold = demo && demo.meta ? demo.meta.threshold : 0.5;
  return Number(value) >= threshold ? "Giả" : "Thật";
}

function countTopTokens(reviews) {
  const counts = new Map();
  const stopWords = new Set([
    "the", "a", "an", "and", "or", "but", "is", "was", "were", "be", "been",
    "it", "this", "that", "i", "my", "me", "we", "our", "you", "your", "they",
    "them", "their", "to", "of", "in", "on", "for", "with", "at", "as", "so",
    "very", "just", "not", "have", "has", "had", "do", "does", "did", "if",
    "from", "would", "could", "should", "there", "here", "one", "get", "got"
  ]);
  let totalWords = 0;

  for (let i = 0; i < reviews.length; i++) {
    const tokens = String(reviews[i].text || "")
      .toLowerCase()
      .match(/[a-z][a-z']+/g) || [];
    totalWords += tokens.length;
    for (let j = 0; j < tokens.length; j++) {
      const token = tokens[j];
      if (token.length < 3 || stopWords.has(token)) {
        continue;
      }
      counts.set(token, (counts.get(token) || 0) + 1);
    }
  }

  const top = Array.from(counts.entries())
    .sort(function (a, b) { return b[1] - a[1]; })
    .slice(0, 10);
  return { totalWords, uniqueWords: counts.size, top };
}

function makeTokenChart(tokens) {
  const width = 560;
  const rowHeight = 24;
  const height = tokens.length * rowHeight + 16;
  const left = 130;
  const barMax = width - left - 56;
  let maxCount = 1;
  for (let i = 0; i < tokens.length; i++) {
    maxCount = Math.max(maxCount, tokens[i][1]);
  }

  const svg = createSvg("svg", {
    viewBox: "0 0 " + width + " " + height,
    role: "img",
    class: "result-chart"
  });
  for (let i = 0; i < tokens.length; i++) {
    const y = 8 + i * rowHeight;
    const barWidth = (tokens[i][1] / maxCount) * barMax;
    svg.appendChild(textNode(left - 8, y + 12, tokens[i][0], "end"));
    svg.appendChild(
      createSvg("rect", {
        x: left, y: y + 2, width: barWidth, height: 14, rx: 3,
        fill: themeColor("--chart-fake", "#2563eb")
      })
    );
    svg.appendChild(
      textNode(left + barWidth + 6, y + 13, countText(tokens[i][1]), "start")
    );
  }
  return svg;
}

function makeMiniHistogram(histogram, threshold) {
  const width = 560;
  const height = 220;
  const left = 44;
  const right = 12;
  const top = 12;
  const bottom = 34;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  let maxValue = 1;
  for (let i = 0; i < histogram.real_counts.length; i++) {
    maxValue = Math.max(maxValue, histogram.real_counts[i], histogram.fake_counts[i]);
  }

  const svg = createSvg("svg", {
    viewBox: "0 0 " + width + " " + height,
    role: "img",
    class: "result-chart"
  });
  const binWidth = plotWidth / histogram.real_counts.length;
  const barWidth = Math.max(2, (binWidth - 4) / 2);

  for (let i = 0; i < histogram.real_counts.length; i++) {
    const x = left + i * binWidth + 2;
    const realHeight = (histogram.real_counts[i] / maxValue) * plotHeight;
    const fakeHeight = (histogram.fake_counts[i] / maxValue) * plotHeight;
    svg.appendChild(
      createSvg("rect", {
        x: x, y: top + plotHeight - realHeight, width: barWidth, height: realHeight,
        fill: themeColor("--chart-real", "#8fa0b6")
      })
    );
    svg.appendChild(
      createSvg("rect", {
        x: x + barWidth, y: top + plotHeight - fakeHeight, width: barWidth,
        height: fakeHeight, fill: themeColor("--chart-fake", "#2563eb")
      })
    );
  }

  const thresholdX = left + threshold * plotWidth;
  svg.appendChild(
    createSvg("line", {
      x1: thresholdX, y1: top, x2: thresholdX, y2: top + plotHeight,
      stroke: themeColor("--chart-marker", "#16202f"),
      "stroke-width": 2, "stroke-dasharray": "5 4"
    })
  );
  svg.appendChild(textNode(left, height - 8, "0.0", "start"));
  svg.appendChild(textNode(left + plotWidth / 2, height - 8, "0.5", "middle"));
  svg.appendChild(textNode(left + plotWidth, height - 8, "1.0", "end"));
  svg.appendChild(textNode(left - 6, top + 4, countText(maxValue), "end"));
  return svg;
}

function makeMiniCurve(points, bestThreshold) {
  const width = 560;
  const height = 220;
  const left = 44;
  const right = 12;
  const top = 12;
  const bottom = 34;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const first = points[0].threshold;
  const last = points[points.length - 1].threshold;

  function xOf(value) {
    return left + ((value - first) / (last - first)) * plotWidth;
  }
  function yOf(value) {
    return top + plotHeight - value * plotHeight;
  }

  const svg = createSvg("svg", {
    viewBox: "0 0 " + width + " " + height,
    role: "img",
    class: "result-chart"
  });
  for (let i = 0; i <= 4; i++) {
    const value = i / 4;
    svg.appendChild(
      createSvg("line", {
        x1: left, y1: yOf(value), x2: left + plotWidth, y2: yOf(value),
        stroke: themeColor("--chart-grid", "#d9e2ee"), "stroke-width": 1
      })
    );
    svg.appendChild(textNode(left - 6, yOf(value) + 4, value.toFixed(1), "end"));
  }

  const series = [
    ["precision", themeColor("--chart-s1", "#8fa0b6")],
    ["recall", themeColor("--chart-s2", "#5b9bff")],
    ["f1", themeColor("--chart-s3", "#2563eb")]
  ];
  for (let s = 0; s < series.length; s++) {
    let pathData = "";
    for (let i = 0; i < points.length; i++) {
      pathData += (i === 0 ? "M" : "L") +
        xOf(points[i].threshold).toFixed(2) + " " +
        yOf(points[i][series[s][0]]).toFixed(2) + " ";
    }
    svg.appendChild(
      createSvg("path", {
        d: pathData, fill: "none", stroke: series[s][1], "stroke-width": 2.2
      })
    );
  }

  const markerX = xOf(bestThreshold);
  svg.appendChild(
    createSvg("line", {
      x1: markerX, y1: top, x2: markerX, y2: top + plotHeight,
      stroke: themeColor("--chart-marker", "#16202f"),
      "stroke-width": 2, "stroke-dasharray": "5 4"
    })
  );
  svg.appendChild(textNode(left, height - 8, first.toFixed(2), "start"));
  svg.appendChild(textNode(left + plotWidth, height - 8, last.toFixed(2), "end"));
  return svg;
}

function makeMiniReliability(calibration) {
  const width = 560;
  const height = 220;
  const left = 44;
  const right = 12;
  const top = 12;
  const bottom = 34;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  function xOf(value) { return left + value * plotWidth; }
  function yOf(value) { return top + plotHeight - value * plotHeight; }

  const svg = createSvg("svg", {
    viewBox: "0 0 " + width + " " + height,
    role: "img",
    class: "result-chart"
  });
  svg.appendChild(
    createSvg("line", {
      x1: xOf(0), y1: yOf(0), x2: xOf(1), y2: yOf(1),
      stroke: themeColor("--chart-real", "#8fa0b6"),
      "stroke-width": 2, "stroke-dasharray": "5 4"
    })
  );

  const bins = calibration.reliability_bins;
  let maxCount = 1;
  for (let i = 0; i < bins.length; i++) {
    maxCount = Math.max(maxCount, bins[i].count);
  }
  for (let i = 0; i < bins.length; i++) {
    if (bins[i].count === 0 || bins[i].mean_predicted === null) {
      continue;
    }
    svg.appendChild(
      createSvg("circle", {
        cx: xOf(bins[i].mean_predicted),
        cy: yOf(bins[i].observed_fake_rate),
        r: 4 + (bins[i].count / maxCount) * 7,
        fill: themeColor("--chart-band", "rgba(37, 99, 235, 0.35)"),
        stroke: themeColor("--chart-s3", "#2563eb"),
        "stroke-width": 1.5
      })
    );
  }
  svg.appendChild(textNode(left, height - 8, "0.0", "start"));
  svg.appendChild(textNode(left + plotWidth, height - 8, "1.0", "end"));
  return svg;
}

function makeResultKpis(testMetrics) {
  const grid = createDiv("kpi-grid");
  const items = [
    ["Accuracy", testMetrics.accuracy],
    ["Precision", testMetrics.precision],
    ["Recall", testMetrics.recall],
    ["F1", testMetrics.f1],
    ["ROC-AUC", testMetrics.roc_auc],
    ["PR-AUC", testMetrics.pr_auc]
  ];
  for (let i = 0; i < items.length; i++) {
    const card = createDiv(i === 3 ? "kpi is-highlight" : "kpi");
    card.appendChild(createDiv("kpi-label", items[i][0]));
    card.appendChild(createDiv("kpi-value", percentText(items[i][1])));
    grid.appendChild(card);
  }
  return grid;
}

function makeResultConfusion(matrix) {
  const grid = createDiv("confusion-grid");
  grid.appendChild(createDiv("confusion-axis", ""));
  grid.appendChild(createDiv("confusion-axis", "Dự đoán: Thật"));
  grid.appendChild(createDiv("confusion-axis", "Dự đoán: Giả"));
  grid.appendChild(createDiv("confusion-axis", "Thực tế: Thật"));
  grid.appendChild(createDiv("confusion-cell cell-tn", "TN " + countText(matrix.tn)));
  grid.appendChild(createDiv("confusion-cell cell-fp", "FP " + countText(matrix.fp)));
  grid.appendChild(createDiv("confusion-axis", "Thực tế: Giả"));
  grid.appendChild(createDiv("confusion-cell cell-fn", "FN " + countText(matrix.fn)));
  grid.appendChild(createDiv("confusion-cell cell-tp", "TP " + countText(matrix.tp)));
  return grid;
}

function getResultStages() {
  const demo = state.demoData;
  const meta = demo.meta;
  const technical = demo.technical;
  const dataset = technical.metrics.dataset;
  const testMetrics = technical.metrics.test;
  const reviews = Array.isArray(demo.reviews) ? demo.reviews : [];

  return [
    {
      name: "1. Khởi tạo",
      build: function () {
        const root = createDiv("result-stage");
        const block = resultBlock(
          "Cấu hình mô hình",
          "Các giá trị này do bước huấn luyện ghi vào data_meta.js."
        );
        block.appendChild(makeResultTable(["Thông tin", "Giá trị"], [
          ["Mô hình", meta.model],
          ["Ngưỡng quyết định", meta.threshold.toFixed(2)],
          ["Lần chạy model", "#" + (meta.model_run_id || "?")],
          ["Phiên bản dữ liệu", meta.data_version || "?"],
          ["Thời điểm sinh", meta.generated_at || "?"],
          ["Số đặc trưng TF-IDF", countText(dataset.n_features)]
        ]));
        root.appendChild(block);

        const note = resultBlock(
          "Chạy huấn luyện thật",
          "Trang web chỉ trình bày lại kết quả đã lưu trong dự án."
        );
        note.appendChild(
          createDiv("hint", "Để huấn luyện lại từ đầu: $env:PYTHONIOENCODING='utf-8'; python MaNguon\\train_baseline.py")
        );
        root.appendChild(note);
        return root;
      }
    },
    {
      name: "2. Dữ liệu",
      build: function () {
        const root = createDiv("result-stage");
        const split = resultBlock(
          "Ba tập dữ liệu",
          "Mỗi tập giữ một vai trò riêng, không gộp vào nhau."
        );
        split.appendChild(makeResultTable(["Tập", "Số review", "Vai trò"], [
          ["train", countText(dataset.rows_train), "Học trọng số TF-IDF và bộ phân loại"],
          ["val", countText(dataset.rows_val), "Hiệu chuẩn xác suất, chọn ngưỡng"],
          ["test", countText(dataset.rows_test), "Chấm điểm cuối, giữ kín đến khi chốt"]
        ]));
        root.appendChild(split);

        const preview = resultBlock(
          "Preview review đầu vào",
          countText(reviews.length) + " dòng của tập test, nạp dần khi cuộn."
        );
        const rows = [];
        for (let i = 0; i < reviews.length; i++) {
          const review = reviews[i];
          rows.push([
            review.row_index,
            shortText(review.text, 90),
            review.rating,
            review.true_label === 1 ? "Giả" : "Thật",
            percentText(review.prob_fake)
          ]);
        }
        preview.appendChild(
          makeInfiniteResultTable(
            ["#", "Nội dung", "Sao", "Nhãn thật", "Xác suất giả"], rows
          )
        );
        root.appendChild(preview);
        return root;
      }
    },
    {
      name: "3. Đặc trưng",
      build: function () {
        const tokenInfo = countTopTokens(reviews);
        const root = createDiv("result-stage");
        const stats = resultBlock(
          "Thống kê token",
          "Đếm trực tiếp trên các review trong trình duyệt."
        );
        stats.appendChild(makeResultTable(["Chỉ số", "Giá trị"], [
          ["Tổng số từ", countText(tokenInfo.totalWords)],
          ["Từ khác nhau (bỏ stopword)", countText(tokenInfo.uniqueWords)],
          ["Trung bình mỗi review", (tokenInfo.totalWords / Math.max(1, reviews.length)).toFixed(1)],
          ["Đặc trưng TF-IDF đã lưu", countText(dataset.n_features)]
        ]));
        root.appendChild(stats);

        const chart = resultBlock(
          "Từ xuất hiện nhiều nhất",
          "Mười từ thông tin xuất hiện nhiều nhất sau khi bỏ stopword."
        );
        chart.appendChild(makeTokenChart(tokenInfo.top));
        root.appendChild(chart);
        return root;
      }
    },
    {
      name: "4. Xác suất",
      build: function () {
        const root = createDiv("result-stage");
        const chart = resultBlock(
          "Phân bố xác suất trên tập test",
          "Xám là nhãn thật, xanh là nhãn giả; nét đứt là ngưỡng " +
          meta.threshold.toFixed(2) + "."
        );
        chart.appendChild(makeMiniHistogram(technical.histogram, meta.threshold));
        root.appendChild(chart);

        const preview = resultBlock(
          "Preview dự đoán",
          "Tất cả review cùng xác suất đã hiệu chuẩn, nạp dần khi cuộn."
        );
        const rows = [];
        for (let i = 0; i < reviews.length; i++) {
          const review = reviews[i];
          rows.push([
            review.row_index,
            shortText(review.text, 60),
            percentText(review.prob_fake),
            labelText(review.prob_fake),
            review.true_label === review.predicted_label ? "Đúng" : "Sai"
          ]);
        }
        preview.appendChild(
          makeInfiniteResultTable(
            ["#", "Nội dung", "Xác suất giả", "Dự đoán", "So với nhãn thật"], rows
          )
        );
        root.appendChild(preview);
        return root;
      }
    },
    {
      name: "5. Đánh giá",
      build: function () {
        const root = createDiv("result-stage");
        const kpi = resultBlock(
          "Chỉ số trên tập test",
          "Đo sau khi ngưỡng đã chốt trên tập val."
        );
        kpi.appendChild(makeResultKpis(testMetrics));
        root.appendChild(kpi);

        const matrix = resultBlock(
          "Ma trận nhầm",
          "Hàng là nhãn thật, cột là nhãn dự đoán."
        );
        matrix.appendChild(makeResultConfusion(testMetrics.confusion_matrix));
        root.appendChild(matrix);

        const validation = technical.metrics.validation;
        const curve = resultBlock(
          "Chọn ngưỡng trên tập val",
          "F1 đạt đỉnh tại ngưỡng " + validation.best_threshold.toFixed(2) +
          " (F1 " + percentText(validation.best_f1) + ")."
        );
        curve.appendChild(makeMiniCurve(technical.threshold_curve, meta.threshold));
        root.appendChild(curve);
        return root;
      }
    },
    {
      name: "6. Tổng hợp",
      build: function () {
        const root = createDiv("result-stage");
        const log = resultBlock(
          "Nhật ký các bước",
          "Kết quả cuối cùng của từng giai đoạn vừa chạy."
        );
        const rows = [];
        for (let i = 0; i < loaderState.steps.length; i++) {
          rows.push([i + 1, loaderState.steps[i].name, loaderState.steps[i].result]);
        }
        log.appendChild(makeResultTable(["#", "Giai đoạn", "Kết quả"], rows));
        root.appendChild(log);

        const calibration = technical.metrics.calibration;
        const reliability = resultBlock(
          "Độ tin cậy của xác suất",
          "Brier " + calibration.brier_before + " → " + calibration.brier_after +
          " · ECE " + calibration.ece_before + " → " + calibration.ece_after + "."
        );
        reliability.appendChild(makeMiniReliability(calibration));
        root.appendChild(reliability);
        return root;
      }
    }
  ];
}

function renderResultStage(index) {
  activeResultStage = index;
  const content = document.getElementById("result-content");
  if (!content) {
    return;
  }

  const tabs = document.querySelectorAll("#result-tabs .result-tab");
  for (let i = 0; i < tabs.length; i++) {
    const isActive = i === index;
    tabs[i].classList.toggle("is-active", isActive);
    tabs[i].setAttribute("aria-selected", isActive ? "true" : "false");
  }

  content.replaceChildren();
  const demo = state.demoData;
  if (!demo || !Array.isArray(demo.reviews) || demo.reviews.length === 0) {
    content.appendChild(resultBlock(
      "Chưa nạp được dữ liệu review",
      "Hãy chạy python MaNguon\\export_web_data.py rồi tải lại trang."
    ));
    return;
  }

  const stages = getResultStages();
  if (stages[index]) {
    content.appendChild(stages[index].build());
  }
}

function buildResultTabs() {
  const container = document.getElementById("result-tabs");
  if (!container) {
    return;
  }
  container.replaceChildren();

  const stages = getResultStages();
  for (let i = 0; i < stages.length; i++) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = i === activeResultStage ? "result-tab is-active" : "result-tab";
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", i === activeResultStage ? "true" : "false");
    button.textContent = stages[i].name;
    button.addEventListener("click", function () {
      renderResultStage(i);
    });
    container.appendChild(button);
  }
}

function showResultPanel() {
  const screen = document.getElementById("loader-screen");
  const panel = document.getElementById("result-panel");
  const thinking = document.getElementById("loader-panel");
  if (!screen || !panel) {
    return;
  }

  // Thinking đã xong: dừng đồng hồ và mở khoá nút "Chạy lại" trong result panel.
  window.clearInterval(loaderState.timerId);
  loaderState.timerId = 0;
  document.body.classList.remove("is-processing");

  if (thinking) {
    thinking.hidden = true;
  }
  panel.hidden = false;
  screen.classList.add("is-result");

  // Đổi nội dung trong cùng một khung nút, không thêm/bớt nút làm xô bố cục.
  const cancelButton = document.getElementById("loader-cancel");
  if (cancelButton) {
    cancelButton.hidden = true;
  }
  const resultActions = document.getElementById("result-actions");
  if (resultActions) {
    resultActions.hidden = false;
  }
  // Header chỉ có một nút chạy: trước là Chạy file, sau là Chạy lại.
  const headerRun = document.getElementById("train-button");
  if (headerRun) {
    headerRun.textContent = "Chạy lại quá trình";
  }

  const demo = state.demoData;
  const subtitle = document.getElementById("result-subtitle");
  if (subtitle) {
    subtitle.textContent = demo
      ? countText(demo.meta.rows_test) + " review test · ngưỡng " +
        demo.meta.threshold.toFixed(2) + " · F1 " +
        percentText(demo.technical.metrics.test.f1) +
        ". Chọn tab để xem chi tiết từng giai đoạn."
      : "Chọn tab để xem chi tiết.";
  }

  const note = document.getElementById("result-note");
  if (note) {
    note.textContent = "Đây là kết quả đã lưu trong dự án, được trình bày lại theo từng bước.";
  }

  activeResultStage = 0;
  buildResultTabs();
  renderResultStage(0);
}

function closeResultPanel() {
  // Phải đọc kế hoạch trước khi hideLoader()/applyPayload() dựng lại các ô số.
  const rushPlan = collectSkeletonRushPlan();
  loading_skeleton(false);
  hideLoader();

  const demo = state.demoData;
  if (!demo) {
    return;
  }
  demo.reviews = Array.isArray(demo.reviews) ? demo.reviews : [];
  applyPayload(demo, "demo");
  setPayloadVisibility(true);
  updateSourceNote();
  renderBadges();
  applyRushPlan(rushPlan);

  // Đóng xong thì đưa người xem thẳng tới thẻ có các con số đang chạy tăng tốc.
  const summaryCard = document.getElementById("summary-card");
  if (summaryCard) {
    summaryCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// Huỷ khi đang thinking: dừng luồng, ẩn loader, đưa các thẻ kết quả về trạng
// thái trước khi bấm chạy. Không áp số liệu và không cuộn trang.
function cancelProcessing() {
  if (!document.body.classList.contains("is-processing")) {
    return;
  }
  loaderState.cancelled = true;
  hideLoader();
  setPayloadVisibility(loaderState.cardsVisible === true);

  const message = "Đã huỷ quá trình. Dữ liệu preview giữ nguyên.";
  const statusId = state.source === "upload" ? "editor-status" : "preview-status";
  const status = document.getElementById(statusId);
  if (status) {
    status.textContent = message;
  }
}

/* ============================================================
   Tiện ích dùng chung
   ============================================================ */

function createSvg(name, attributes) {
  const element = document.createElementNS(SVG_NAMESPACE, name);
  const keys = Object.keys(attributes);
  for (let i = 0; i < keys.length; i++) {
    element.setAttribute(keys[i], attributes[keys[i]]);
  }
  return element;
}

function createDiv(className, text) {
  const element = document.createElement("div");
  if (className) {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}

function percentText(value) {
  return (value * 100).toFixed(2) + "%";
}

function countText(value) {
  return Number(value).toLocaleString("vi-VN");
}

function textNode(x, y, text, anchor, fill) {
  const node = createSvg("text", {
    x: x,
    y: y,
    "text-anchor": anchor || "start",
    "font-size": 12,
    fill: fill || themeColor("--muted", "#59677d")
  });
  node.textContent = text;
  return node;
}

function makeTag(text, className) {
  const element = document.createElement("span");
  element.className = "tag " + className;
  element.textContent = text;
  return element;
}

// Tag bấm được trong từng dòng bảng. Dùng button để có focus và :active, nhưng
// vẫn mang class .tag/.category-tag để giữ nguyên màu cũ.
function makeActionTag(text, className, onClick, title) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = className + " tag-button";
  element.textContent = text;
  if (title) {
    element.title = title;
  }
  element.addEventListener("click", function (event) {
    event.stopPropagation();
    onClick();
  });
  return element;
}

function makeTextCell(text, className) {
  const cell = document.createElement("td");
  if (className) {
    cell.className = className;
  }
  cell.textContent = text;
  return cell;
}

function categoryInfo(categoryId) {
  if (CATEGORY_INFO[categoryId]) {
    return CATEGORY_INFO[categoryId];
  }
  return { label: categoryId, tone: "muted", description: "" };
}

// CSS dùng class "cat-<id>" để tô màu riêng cho từng nhóm.
// Vì sao tách khỏi "tone": tone chỉ có 4 màu, còn 5 nhóm cần 5 màu khác nhau.
function categoryClass(categoryId) {
  return "cat-" + categoryId;
}

// Cơ sở của nhóm, khớp hàm category_basis_for_category trong MaNguon/classify.py.
// Vì sao tính cả ở JS: dữ liệu cũ có thể chưa có trường category_basis.
function basisForCategory(categoryId) {
  if (categoryId === "low_content" || categoryId === "spam_duplicate") {
    return "rule";
  }
  if (categoryId === "suspected_bot_boost") {
    return "model+rule";
  }
  return "model";
}

function basisClass(basis) {
  if (basis === "rule") {
    return "basis-rule";
  }
  if (basis === "model+rule") {
    return "basis-both";
  }
  return "basis-model";
}

function basisLabel(basis) {
  return BASIS_LABELS[basis] || basis || "MODEL";
}

function makeBasisTag(basis) {
  const tag = document.createElement("span");
  tag.className = "basis-tag " + basisClass(basis);
  tag.textContent = basisLabel(basis);
  return tag;
}

function formatReason(codeEntry) {
  // Dữ liệu cũ có thể là câu đầy đủ; dữ liệu mới là [mã, tham số...].
  if (!Array.isArray(codeEntry)) {
    return String(codeEntry);
  }

  const code = codeEntry[0];
  const template = REASON_TEMPLATES[code];
  if (!template) {
    return String(code);
  }

  let text = template;
  for (let i = 1; i < codeEntry.length; i++) {
    text = text.split("{" + (i - 1) + "}").join(String(codeEntry[i]));
  }
  return text;
}

function reviewReasonTexts(review) {
  if (Array.isArray(review.reason_codes)) {
    const texts = [];
    for (let i = 0; i < review.reason_codes.length; i++) {
      texts.push(formatReason(review.reason_codes[i]));
    }
    return texts;
  }

  if (Array.isArray(review.reasons)) {
    return review.reasons;
  }

  return [];
}

function makeCategoryTag(categoryId, interactive) {
  const info = categoryInfo(categoryId);
  const className = "category-tag " + categoryClass(categoryId);

  if (!interactive) {
    const tag = document.createElement("span");
    tag.className = className;
    tag.appendChild(document.createTextNode(info.label));
    return tag;
  }

  return makeActionTag(
    info.label,
    className,
    function () {
      setFilter(categoryId);
    },
    "Lọc theo nhóm: " + info.label
  );
}

// Gom rating lẻ về số nguyên giống cột phân bố 5 sao. Trả về null khi không
// có rating hợp lệ để các phép lọc không biến 0 thành "0 sao".
function roundedStar(rating) {
  if (rating === null || rating === undefined) {
    return null;
  }
  const value = Math.round(Number(rating));
  return isNaN(value) || value < 1 || value > 5 ? null : value;
}

function starNumber() {
  return state.star === "all" ? null : Number(state.star);
}

function starsText(rating) {
  if (rating === null || rating === undefined) {
    return "—";
  }

  const value = Math.round(Number(rating));
  if (isNaN(value) || value < 1 || value > 5) {
    return "—";
  }

  // "★".repeat(n): lặp ký tự sao đặc; phần còn lại là sao rỗng.
  return "★".repeat(value) + "☆".repeat(5 - value);
}

/* ============================================================
   Thẻ nhóm và số review hữu ích
   ============================================================ */

function renderSummary() {
  const container = document.getElementById("category-grid");
  container.innerHTML = "";

  const summary = state.summary;
  const total = summary.total;

  for (let i = 0; i < CATEGORY_ORDER.length; i++) {
    const categoryId = CATEGORY_ORDER[i];
    const info = categoryInfo(categoryId);
    const count = summary.categories[categoryId] || 0;
    const percent = total > 0 ? (count / total) * 100 : 0;

    const card = document.createElement("button");
    card.type = "button";
    card.className =
      "category-card tone-" + info.tone + " " + categoryClass(categoryId);
    // playCardEntrance() đọc id này để gán animation-delay riêng cho từng nhóm.
    card.dataset.category = categoryId;
    if (state.filter === categoryId) {
      card.className = card.className + " is-active";
    }

    // Huy hiệu góc trên phải: chữ của chính nhóm, thay cho icon/huy chương.
    // Vì sao dùng chữ: người xem đọc được ngay tên nhóm, không phải đoán hình.
    const badge = createDiv("category-badge", info.label);
    card.appendChild(badge);

    const topLine = createDiv("category-top");
    topLine.appendChild(createDiv("category-label", info.label));
    card.appendChild(topLine);

    const finalCountText = countText(count);
    const finalPercentText = percent.toFixed(1) + "%";
    const countNode = createDiv(
      "category-count",
      revealPending ? "0" : finalCountText
    );
    const percentNode = createDiv(
      "category-percent",
      revealPending ? "0%" : finalPercentText
    );
    // Giữ số thật ở dataset để nút "Hiện lại dữ liệu" biết đích cần chạy tới.
    countNode.dataset.finalText = finalCountText;
    percentNode.dataset.finalText = finalPercentText;
    card.appendChild(countNode);
    card.appendChild(percentNode);

    const bar = createDiv("category-bar");
    const fill = createDiv("category-bar-fill");
    fill.style.width = revealPending ? "0%" : percent + "%";
    // Mốc để reportRushProgress() chạy thanh từ 0 lên đúng tỉ lệ của nhóm.
    fill.dataset.finalWidth = percent + "%";
    if (revealPending) {
      fill.dataset.rushProgress = "0";
    }
    bar.appendChild(fill);
    card.appendChild(bar);

    card.appendChild(createDiv("category-description", info.description));

    // Nhãn cơ sở đặt dưới mô tả, tách khỏi huy hiệu góc trên phải.
    // Vì sao cần: người xem biết ngay con số này do model hay do luật quyết định.
    const basisRow = createDiv("category-basis");
    basisRow.appendChild(makeBasisTag(basisForCategory(categoryId)));
    card.appendChild(basisRow);

    card.addEventListener("click", function () {
      setFilter(categoryId);
    });

    container.appendChild(card);
  }

  const usefulPercent = total > 0 ? (summary.useful_count / total) * 100 : 0;
  const pill = document.getElementById("useful-pill");
  pill.innerHTML = "";
  pill.appendChild(createDiv("useful-pill-value", countText(summary.useful_count)));
  pill.appendChild(
    createDiv(
      "useful-pill-label",
      "review được giữ lại / " + countText(total) + " (" + usefulPercent.toFixed(1) + "%)"
    )
  );

  const hint = document.getElementById("summary-hint");
  if (state.source === "demo") {
    hint.textContent =
      "Trên toàn bộ " + countText(total) + " review test. Đã loại " +
      countText(summary.removed_count) + " review không hữu ích.";
  } else {
    hint.textContent =
      "Trên " + countText(total) + " dòng phân tích từ file tải lên. Đã loại " +
      countText(summary.removed_count) + " dòng không hữu ích.";
  }
}

/* ============================================================
   Bảng phân bố 5 sao
   ============================================================ */

function makeStarMeter(value, maxValue, fillClass, options) {
  const settings = options || {};
  const interactive = Boolean(settings.interactive);

  const cell = interactive ? document.createElement("button") : createDiv("star-meter");
  if (interactive) {
    cell.type = "button";
    cell.className = "star-meter star-meter-button";
    cell.dataset.star = String(settings.star);
    cell.dataset.scope = settings.scope;
    cell.disabled = value === 0;
    const scopeName = settings.scope === "all" ? "Tất cả" : "Sau khi lọc hữu ích";
    cell.setAttribute(
      "aria-label",
      scopeName + ", " + settings.star + " sao, " + countText(value) +
      " review. Bấm để lọc bảng."
    );
  }

  const track = createDiv("star-meter-track");
  const fill = createDiv("star-meter-fill " + fillClass);
  const width = maxValue > 0 ? (value / maxValue) * 100 : 0;
  const finalWidth = Math.min(100, width) + "%";
  fill.style.width = revealPending ? "0%" : finalWidth;
  fill.dataset.finalWidth = finalWidth;
  track.appendChild(fill);

  const finalCountText = countText(value);
  const countNode = createDiv(
    "star-meter-count",
    revealPending ? "0" : finalCountText
  );
  countNode.dataset.finalText = finalCountText;
  cell.appendChild(track);
  cell.appendChild(countNode);

  if (interactive) {
    const scopeFilter = settings.scope === "all" ? "all" : "genuine";
    const active = state.star === String(settings.star) &&
      state.filter === scopeFilter;
    if (active) {
      cell.classList.add("is-active");
    }
    cell.setAttribute("aria-pressed", active ? "true" : "false");
    cell.addEventListener("click", function () {
      selectStarFromMeter(settings.star, settings.scope);
    });
  }

  return cell;
}

// Nhịp nảy rất nhẹ đúng thanh vừa bấm. Class tự tháo để hover lại thuộc về CSS.
function pulseStarMeter(meter) {
  if (reducedMotionEnabled() || !meter) {
    return;
  }
  meter.classList.remove("is-pulsing");
  // Bắt đầu lại animation ngay cả khi bấm liên tiếp cùng một thanh.
  void meter.offsetWidth;
  meter.classList.add("is-pulsing");
  meter.addEventListener("animationend", function done(event) {
    if (event.animationName !== "meter-pulse") {
      return;
    }
    meter.removeEventListener("animationend", done);
    meter.classList.remove("is-pulsing");
  });
}

function renderStarPanel() {
  const container = document.getElementById("star-panel");
  container.innerHTML = "";

  const summary = state.summary;

  let maxAll = 1;
  let totalRated = 0;
  for (let i = 0; i < 5; i++) {
    maxAll = Math.max(maxAll, summary.star_all[i]);
    totalRated = totalRated + summary.star_all[i];
  }

  const header = createDiv("star-row star-head");
  header.appendChild(createDiv("star-rating", "Sao"));
  header.appendChild(createDiv("star-meter star-meter-head", "Tất cả"));
  header.appendChild(createDiv("star-meter star-meter-head", "Sau khi lọc hữu ích"));
  header.appendChild(createDiv("star-removed", "Bị loại"));
  container.appendChild(header);

  for (let value = 5; value >= 1; value--) {
    const index = value - 1;
    const allCount = summary.star_all[index];
    const usefulCount = summary.star_useful[index];
    const removedCount = allCount - usefulCount;

    const row = createDiv("star-row");
    if (state.star === String(value)) {
      row.classList.add("is-star-selected");
    }

    const ratingCell = createDiv("star-rating");
    ratingCell.appendChild(createDiv("star-glyphs", starsText(value)));
    ratingCell.appendChild(createDiv("star-value", value + " sao"));
    row.appendChild(ratingCell);

    row.appendChild(makeStarMeter(allCount, maxAll, "fill-all", {
      interactive: true,
      star: value,
      scope: "all"
    }));
    row.appendChild(makeStarMeter(usefulCount, maxAll, "fill-useful", {
      interactive: true,
      star: value,
      scope: "useful"
    }));

    const removedText = removedCount > 0 ? "−" + countText(removedCount) : "0";
    row.appendChild(createDiv("star-removed", removedText));

    container.appendChild(row);
  }

  const note = document.getElementById("star-note");
  if (totalRated === 0) {
    note.textContent = "Không có review nào có rating hợp lệ trong nguồn dữ liệu này.";
  } else if (summary.star_missing_all > 0) {
    note.textContent =
      "Tổng review có rating: " + countText(totalRated) +
      ". Số review không có rating hợp lệ: " + countText(summary.star_missing_all) + ".";
  } else {
    note.textContent = "Tổng review có rating: " + countText(totalRated) + ".";
  }
}

/* ============================================================
   Bộ lọc
   ============================================================ */

function scrollTableIntoView() {
  const tableCard = document.getElementById("table-card");
  if (tableCard) {
    tableCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// Vẽ lại đúng những phần bị bộ lọc làm thay đổi. Không gọi renderSummary() ở
// setStar/setQuery: số ở thẻ nhóm là số gốc của cả tập, không đổi theo tìm kiếm.
function renderFilterViews() {
  renderSummary();
  renderStarPanel();
  renderFilterChips();
  renderStarMenu();
  renderActiveFilters();
  renderTable();
}

function setFilter(filterId) {
  state.filter = filterId;
  state.currentPage = 1;
  renderFilterViews();
  scrollTableIntoView();
}

function setStar(starKey) {
  state.star = starKey;
  state.currentPage = 1;
  renderStarPanel();
  renderStarMenu();
  renderActiveFilters();
  renderTable();
}

// Click thanh trong biểu đồ: cột "Tất cả" đặt nhóm về Tất cả, cột "Sau khi lọc"
// đặt nhóm về Hữu ích. Bấm đúng thanh đang active thì chỉ bỏ sao, giữ nhóm.
function selectStarFromMeter(value, scope) {
  const targetFilter = scope === "all" ? "all" : "genuine";
  const starKey = String(value);
  const wasActive = state.star === starKey && state.filter === targetFilter;

  state.star = wasActive ? "all" : starKey;
  state.filter = targetFilter;
  state.currentPage = 1;
  renderFilterViews();
  pulseStarMeter(document.querySelector(
    '.star-meter-button[data-star="' + starKey + '"][data-scope="' + scope + '"]'
  ));
  scrollTableIntoView();
}

function setFlag(flagName) {
  state.flag = state.flag === flagName ? null : flagName;
  state.currentPage = 1;
  renderStarMenu();
  renderActiveFilters();
  renderTable();
}

function setQuery(query) {
  state.query = query || "";
  const input = document.getElementById("table-search");
  if (input && input.value !== state.query) {
    input.value = state.query;
  }
  state.currentPage = 1;
  renderStarMenu();
  renderActiveFilters();
  renderTable();
}

function renderFilterChips() {
  const container = document.getElementById("filter-chips");
  container.innerHTML = "";

  // Chip lọc chỉ dùng chữ: đồng bộ với thẻ nhóm (đã bỏ icon) và tránh
  // trường hợp info.icon không còn tồn tại.
  const items = [
    { id: "all", label: "Tất cả", count: state.summary.total }
  ];

  for (let i = 0; i < CATEGORY_ORDER.length; i++) {
    const categoryId = CATEGORY_ORDER[i];
    const info = categoryInfo(categoryId);
    items.push({
      id: categoryId,
      label: info.label,
      count: state.summary.categories[categoryId] || 0
    });
  }

  for (let i = 0; i < items.length; i++) {
    const item = items[i];

    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "filter-chip";
    if (state.filter === item.id) {
      chip.className = chip.className + " is-active";
    }

    chip.appendChild(document.createTextNode(item.label));
    chip.appendChild(createDiv("chip-count", countText(item.count)));

    chip.addEventListener("click", function () {
      setFilter(item.id);
    });

    container.appendChild(chip);
  }

  // Dropdown sao nằm ngay sau các chip nhóm, cùng một hàng.
  container.appendChild(buildStarDropdown());
}

/* ============================================================
   Bảng review
   ============================================================ */

// Các dòng sau nhóm + cờ + ô tìm, nhưng trước khi áp sao. Chip sao đếm trên
// cùng một tập này nên số trên chip luôn khớp với bảng khi bấm vào.
function getBaseRows() {
  const group = state.filter;
  const query = foldForSearch(state.query).text;
  const flag = state.flag;
  const rows = [];

  for (let i = 0; i < state.rows.length; i++) {
    const review = state.rows[i];
    if (group !== "all" && review.category !== group) {
      continue;
    }
    if (flag && !(Array.isArray(review.flags) && review.flags.indexOf(flag) !== -1)) {
      continue;
    }
    if (query) {
      const haystack = foldForSearch(
        String(review.text || "") + " " + String(review.product_category || "")
      );
      if (haystack.text.indexOf(query) === -1) {
        continue;
      }
    }
    rows.push(review);
  }
  return rows;
}

function getVisibleRows() {
  const base = getBaseRows();
  const star = starNumber();
  if (star === null) {
    return base;
  }

  const visible = [];
  for (let i = 0; i < base.length; i++) {
    if (roundedStar(base[i].rating) === star) {
      visible.push(base[i]);
    }
  }
  return visible;
}

function renderStarMenu() {
  const menu = document.querySelector("#star-dropdown .star-dropdown-menu");
  const label = document.querySelector("#star-dropdown .star-dropdown-label");
  if (!menu) {
    return;
  }
  if (label) {
    label.textContent = state.star === "all"
      ? "★ Mọi sao"
      : "★ " + state.star + " sao";
  }
  menu.innerHTML = "";

  // Số trên từng mức được tính trên đúng nhóm + cờ + ô tìm hiện tại, nên gõ
  // tìm kiếm là số trong dropdown đổi theo ngay cả khi menu đang mở.
  const base = getBaseRows();
  const counts = [0, 0, 0, 0, 0, 0];
  for (let i = 0; i < base.length; i++) {
    const star = roundedStar(base[i].rating);
    if (star !== null) {
      counts[star]++;
    }
  }

  const items = [{ id: "all", label: "Mọi sao", count: base.length }];
  for (let value = 5; value >= 1; value--) {
    items.push({
      id: String(value),
      label: "★".repeat(value) + " " + value + " sao",
      count: counts[value]
    });
  }

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const option = document.createElement("button");
    option.type = "button";
    option.className = "star-option";
    const active = state.star === item.id;
    if (active) {
      option.className = option.className + " is-active";
    }
    option.setAttribute("role", "option");
    option.setAttribute("aria-selected", active ? "true" : "false");
    option.appendChild(document.createTextNode(item.label));
    option.appendChild(createDiv("chip-count", countText(item.count)));
    option.addEventListener("click", function (event) {
      event.stopPropagation();
      setStar(item.id);
      setStarMenuOpen(false);
    });
    menu.appendChild(option);
  }
}

function setStarMenuOpen(open) {
  const menu = document.querySelector("#star-dropdown .star-dropdown-menu");
  const trigger = document.querySelector("#star-dropdown .star-dropdown-trigger");
  const wrap = document.querySelector("#star-dropdown");
  if (!menu || !trigger || !wrap) {
    return;
  }
  menu.hidden = !open;
  trigger.setAttribute("aria-expanded", open ? "true" : "false");
  wrap.classList.toggle("is-open", open);
}

function buildStarDropdown() {
  const wrap = createDiv("star-dropdown");
  wrap.id = "star-dropdown";

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "filter-chip star-dropdown-trigger";
  trigger.id = "star-dropdown-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");

  const label = createDiv("star-dropdown-label", "★ Mọi sao");
  label.id = "star-dropdown-label";
  trigger.appendChild(label);

  const caret = createDiv("star-dropdown-caret", "▾");
  caret.setAttribute("aria-hidden", "true");
  trigger.appendChild(caret);
  trigger.addEventListener("click", function (event) {
    event.stopPropagation();
    setStarMenuOpen(
      document.querySelector("#star-dropdown .star-dropdown-menu").hidden
    );
  });

  const menu = createDiv("star-dropdown-menu");
  menu.id = "star-dropdown-menu";
  menu.setAttribute("role", "listbox");
  menu.hidden = true;

  wrap.appendChild(trigger);
  wrap.appendChild(menu);
  return wrap;
}

function bindStarDropdown() {
  document.addEventListener("click", function (event) {
    const wrap = document.querySelector("#star-dropdown");
    if (wrap && !wrap.contains(event.target)) {
      setStarMenuOpen(false);
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      setStarMenuOpen(false);
    }
  });
}

// Những bộ lọc không có điều khiển riêng (cờ, chữ tìm) hiện thành nút nhỏ có thể
// bỏ từng cái. Star có dropdown riêng nên không lặp lại ở đây.
function renderActiveFilters() {
  const host = document.getElementById("active-filters");
  if (!host) {
    return;
  }
  host.innerHTML = "";

  const items = [];
  if (state.flag) {
    items.push({
      label: "Cờ: " + (FLAG_INFO[state.flag] || state.flag),
      clear: function () { setFlag(null); }
    });
  }
  if (state.query) {
    items.push({
      label: "Tìm: " + state.query,
      clear: function () { setQuery(""); }
    });
  }

  for (let i = 0; i < items.length; i++) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "active-filter-chip";
    chip.title = "Bỏ bộ lọc này";
    chip.textContent = items[i].label + " ×";
    chip.addEventListener("click", items[i].clear);
    host.appendChild(chip);
  }
}

function renderTableHead() {
  const head = document.getElementById("table-head");
  head.innerHTML = "";

  const row = document.createElement("tr");
  const columns = ["#", "Nội dung review", "Sao", "Nhóm", "Xác suất Giả"];

  // Chỉ dữ liệu demo mới có nhãn thật; file tải lên thì không.
  if (state.hasTrueLabel) {
    columns.push("Nhãn thật");
  }
  columns.push("Cờ");

  for (let i = 0; i < columns.length; i++) {
    const cell = document.createElement("th");
    cell.textContent = columns[i];
    row.appendChild(cell);
  }

  head.appendChild(row);
}

function makeProbabilityCell(probabilityFake, tone) {
  const cell = document.createElement("td");
  cell.className = "prob-cell";
  cell.appendChild(createDiv("prob-number", percentText(probabilityFake)));

  const bar = createDiv("prob-bar");
  const fill = createDiv("prob-fill tone-" + tone);
  fill.style.width = Math.min(100, probabilityFake * 100) + "%";
  bar.appendChild(fill);
  cell.appendChild(bar);

  return cell;
}

function makeReviewRow(review, index) {
  const info = categoryInfo(review.category);

  const tableRow = document.createElement("tr");
  tableRow.className = "row-tone-" + info.tone;

  if (
    review.category === "suspected_fake" ||
    review.category === "suspected_bot_boost" ||
    review.category === "spam_duplicate"
  ) {
    tableRow.className = tableRow.className + " is-suspect";
  }

  // Câu mà model không hiểu (tỷ lệ token quen thấp) bị làm mờ để người xem
  // không nhầm nó với một kết luận đáng tin.
  if (review.is_reliable === false) {
    tableRow.className = tableRow.className + " is-unreliable";
  }

  tableRow.appendChild(makeTextCell(String(index)));

  // Cột nội dung: giữ đầy đủ text, không cắt ngắn.
  const textCell = document.createElement("td");
  textCell.className = "text-cell";
  const reviewText = createDiv("review-text", "");
  appendHighlightedText(reviewText, review.text, state.query);
  textCell.appendChild(reviewText);

  const metaParts = [];
  if (review.product_category) {
    metaParts.push(review.product_category);
  }
  if (review.used_translation) {
    metaParts.push("đã dịch");
  }
  if (review.flag_source) {
    metaParts.push(review.flag_source === "rule" ? "theo luật" : "theo model");
  }
  if (metaParts.length > 0) {
    textCell.appendChild(createDiv("review-meta", metaParts.join(" · ")));
  }

  // Lý do xếp nhóm: mở ra để người xem tự kiểm chứng, không phải tin mù.
  // Dữ liệu mới chỉ có reason_codes; reviewReasonTexts ghép lại thành câu.
  const reasonTexts = reviewReasonTexts(review);
  if (reasonTexts.length > 0) {
    const reasonsBox = document.createElement("details");
    reasonsBox.className = "reasons-details";

    const reasonsSummary = document.createElement("summary");
    reasonsSummary.textContent = "Vì sao xếp nhóm này?";
    reasonsBox.appendChild(reasonsSummary);

    const reasonsList = document.createElement("ul");
    reasonsList.className = "reasons-list";
    for (let i = 0; i < reasonTexts.length; i++) {
      const item = document.createElement("li");
      item.textContent = reasonTexts[i];
      reasonsList.appendChild(item);
    }
    reasonsBox.appendChild(reasonsList);
    textCell.appendChild(reasonsBox);
  }

  // Với file tải lên, cho xem bản dịch mà model thực sự đọc.
  if (review.used_translation && review.translated_text) {
    const details = document.createElement("details");
    details.className = "translation-details";

    const summary = document.createElement("summary");
    summary.textContent = "Bản dịch model đã đọc";
    details.appendChild(summary);

    const paragraph = document.createElement("p");
    paragraph.textContent = review.translated_text;
    details.appendChild(paragraph);

    textCell.appendChild(details);
  }

  tableRow.appendChild(textCell);

  const starCell = document.createElement("td");
  starCell.className = "star-cell";
  const rounded = roundedStar(review.rating);
  const starGlyphs = rounded === null
    ? createDiv("star-glyphs", starsText(review.rating))
    : makeActionTag(
      starsText(review.rating),
      "star-glyphs star-row-tag",
      function () { setStar(String(rounded)); },
      "Lọc " + rounded + " sao"
    );
  starCell.appendChild(starGlyphs);
  if (review.rating !== null && review.rating !== undefined) {
    starCell.appendChild(createDiv("star-number", Number(review.rating).toFixed(1)));
  }
  tableRow.appendChild(starCell);

  const categoryCell = document.createElement("td");
  categoryCell.className = "category-cell";
  categoryCell.appendChild(makeCategoryTag(review.category, true));

  // Nhãn cơ sở ngay dưới tên nhóm, để từng dòng cũng nói rõ model hay luật.
  const rowBasis = review.category_basis
    ? review.category_basis
    : basisForCategory(review.category);
  categoryCell.appendChild(makeBasisTag(rowBasis));
  tableRow.appendChild(categoryCell);

  tableRow.appendChild(makeProbabilityCell(review.prob_fake, info.tone));

  if (state.hasTrueLabel) {
    const truthCell = document.createElement("td");
    truthCell.className = "truth-cell";
    truthCell.appendChild(
      review.true_label === 1
        ? makeTag("Giả", "tag-fake")
        : makeTag("Thật", "tag-real")
    );

    if (review.is_correct === true) {
      truthCell.appendChild(makeTag("đúng", "tag-ok"));
    } else if (review.is_correct === false) {
      truthCell.appendChild(makeTag("sai", "tag-wrong"));
    }

    tableRow.appendChild(truthCell);
  }

  const flagCell = document.createElement("td");
  flagCell.className = "flag-cell";

  // Mọi review đều có cờ sao riêng (1–5), không chỉ riêng five_star. Cờ này
  // được tạo từ rating làm tròn giống biểu đồ, nên dòng 4.4 hiện "4 sao".
  const ratingStar = roundedStar(review.rating);
  if (ratingStar !== null) {
    const starFlagName = "star_" + ratingStar;
    const starFlagLabel = ratingStar + " sao";
    flagCell.appendChild(makeActionTag(
      starFlagLabel,
      "tag-flag flag-star flag-star-" + ratingStar,
      function () { setStar(String(ratingStar)); },
      "Lọc theo số sao: " + starFlagLabel
    ));
  }

  if (review.flags && review.flags.length > 0) {
    for (let i = 0; i < review.flags.length; i++) {
      const flagName = review.flags[i];
      // five_star trùng nghĩa với cờ sao vừa thêm ở trên, nên bỏ bản gốc để
      // không hiện cùng một ý hai lần trong cùng một ô.
      if (flagName === "five_star") {
        continue;
      }
      const flagLabel = FLAG_INFO[flagName] || flagName;
      flagCell.appendChild(makeActionTag(
        flagLabel,
        "tag-flag flag-" + flagName,
        function () { setFlag(flagName); },
        "Lọc theo cờ: " + flagLabel
      ));
    }
  }
  tableRow.appendChild(flagCell);

  return tableRow;
}

function updateTableHeader(visibleCount, startIndex, endIndex) {
  const title = document.getElementById("table-title");
  const hint = document.getElementById("table-hint");
  const count = document.getElementById("table-count");

  if (state.filter === "genuine") {
    title.textContent = "Review hữu ích (đã lọc)";
    hint.textContent =
      "Đã loại " + countText(state.summary.removed_count) +
      " review không hữu ích. Bảng dưới chỉ còn review được giữ lại.";
  } else if (state.filter === "all") {
    title.textContent = "Tất cả review";
    hint.textContent =
      "Bảng gồm cả review hữu ích và review đáng nghi / không hữu ích.";
  } else {
    const info = categoryInfo(state.filter);
    title.textContent = "Review: " + info.label;
    hint.textContent = info.description + ".";
  }

  const filterParts = [];
  if (state.star !== "all") {
    filterParts.push(state.star + " sao");
  }
  if (state.flag) {
    filterParts.push("cờ: " + (FLAG_INFO[state.flag] || state.flag));
  }
  if (filterParts.length > 0) {
    title.textContent = title.textContent + " · " + filterParts.join(" · ");
  }
  if (state.query) {
    hint.textContent = hint.textContent + " Đang tìm “" + state.query + "”.";
  }

  if (visibleCount === 0) {
    count.textContent = "Không có dòng nào khớp bộ lọc.";
  } else {
    count.textContent =
      "Hiển thị " + countText(startIndex + 1) + "–" + countText(endIndex) +
      " / " + countText(visibleCount) + " dòng.";
  }
}

function totalPageCount(rowCount) {
  const pages = Math.ceil(rowCount / state.pageSize);
  // Luôn có ít nhất 1 trang, kể cả khi bộ lọc không còn dòng nào.
  return Math.max(1, pages);
}

function paintPagination(totalPages) {
  document.getElementById("page-label").textContent =
    "Trang " + state.currentPage + " / " + totalPages;

  const isFirstPage = state.currentPage <= 1;
  const isLastPage = state.currentPage >= totalPages;

  document.getElementById("page-first").disabled = isFirstPage;
  document.getElementById("page-prev").disabled = isFirstPage;
  document.getElementById("page-next").disabled = isLastPage;
  document.getElementById("page-last").disabled = isLastPage;
}

function renderTable() {
  const body = document.getElementById("table-body");
  body.innerHTML = "";

  const visibleRows = getVisibleRows();
  const totalPages = totalPageCount(visibleRows.length);

  // Kẹp trang hiện tại vào khoảng hợp lệ. Ví dụ đang ở trang 200 rồi đổi
  // bộ lọc còn 21 trang thì phải nhảy về trang 21, không để bảng trắng.
  if (state.currentPage > totalPages) {
    state.currentPage = totalPages;
  }
  if (state.currentPage < 1) {
    state.currentPage = 1;
  }

  const startIndex = (state.currentPage - 1) * state.pageSize;
  const endIndex = Math.min(startIndex + state.pageSize, visibleRows.length);

  for (let i = startIndex; i < endIndex; i++) {
    body.appendChild(makeReviewRow(visibleRows[i], i + 1));
  }

  updateTableHeader(visibleRows.length, startIndex, endIndex);
  paintPagination(totalPages);
}

/* ============================================================
   Badge đầu trang và ghi chú nguồn
   ============================================================ */

function renderBadges() {
  const container = document.getElementById("header-badges");
  container.innerHTML = "";

  const demoMeta = state.demoData ? state.demoData.meta : null;
  const meta = state.meta || demoMeta;

  const modelName = meta && meta.model
    ? meta.model
    : "Logistic Regression + TF-IDF";
  const threshold = meta && typeof meta.threshold === "number"
    ? meta.threshold
    : null;

  const items = [["Mô hình", modelName]];
  if (threshold !== null) {
    items.push(["Ngưỡng", threshold.toFixed(2)]);
  }
  items.push(["Nguồn", state.source === "demo" ? "Tập test" : "File tải lên"]);
  if (state.rows.length > 0) {
    items.push(["Review", countText(state.rows.length)]);
  }

  for (let i = 0; i < items.length; i++) {
    const badge = createDiv("badge");
    badge.appendChild(document.createTextNode(items[i][0] + ": "));

    const strong = document.createElement("strong");
    strong.textContent = items[i][1];
    badge.appendChild(strong);

    container.appendChild(badge);
  }
}

function updateSourceNote() {
  const note = document.getElementById("source-note");

  if (state.source === "demo") {
    if (state.demoData) {
      note.textContent =
        "Đang xem toàn bộ " + countText(state.demoData.meta.rows_test) +
        " review test, kèm nhãn thật để đối chiếu.";
    } else {
      note.textContent =
        "Chưa có dữ liệu demo. Hãy chạy: python MaNguon/export_web_data.py";
    }
  } else {
    if (state.uploadData) {
      note.textContent =
        "Đang xem " + countText(state.uploadData.meta.analyzed_rows) +
        " dòng từ file " + state.uploadFileName + ".";
    } else if (state.edit.loaded) {
      note.textContent =
        "Đã nạp " + countText(state.edit.rows.length) + " dòng từ " +
        state.edit.fileName + " vào bảng sửa. Bấm Chạy phân tích bảng để chấm.";
    } else {
      note.textContent =
        "Chọn file CSV để nạp vào bảng sửa. Cần chạy server bằng: " +
        "python MaNguon/api_server.py";
    }
  }
}

/* ============================================================
   Chuyển nguồn dữ liệu
   ============================================================ */

function setPayloadVisibility(visible) {
  document.getElementById("summary-card").hidden = !visible;
  document.getElementById("star-card").hidden = !visible;
  document.getElementById("table-card").hidden = !visible;
}

function applyPayload(payload, source) {
  state.rows = payload.reviews ? payload.reviews : payload.rows;
  state.summary = payload.summary;
  state.meta = payload.meta;
  state.hasTrueLabel = source === "demo";
  state.filter = "genuine";
  state.star = "all";
  state.flag = null;
  state.query = "";
  state.currentPage = 1;

  const search = document.getElementById("table-search");
  if (search) {
    search.value = "";
  }
  renderSummary();
  renderStarPanel();
  renderFilterChips();
  renderStarMenu();
  renderActiveFilters();
  renderTableHead();
  renderTable();
}

function switchSource(source) {
  state.source = source;

  document.getElementById("tab-demo").classList.toggle("is-active", source === "demo");
  document.getElementById("tab-upload").classList.toggle("is-active", source === "upload");
  document.getElementById("upload-card").hidden = source !== "upload";

  const payload = source === "demo" ? state.demoData : state.uploadData;

  if (payload) {
    applyPayload(payload, source);
    setPayloadVisibility(true);
  } else {
    state.rows = [];
    state.summary = null;
    state.meta = null;
    setPayloadVisibility(false);
  }

  updateSourceNote();
  renderBadges();
}

/* ============================================================
   Tải file CSV
   ============================================================ */

/* ============================================================
   Tải file CSV, xem trước và sửa bảng
   ============================================================ */

function showUploadWarnings(warnings, isError) {
  const container = document.getElementById("upload-warnings");
  container.innerHTML = "";

  for (let i = 0; i < warnings.length; i++) {
    const box = createDiv(isError ? "predict-warning" : "upload-warning");
    box.textContent = warnings[i];
    container.appendChild(box);
  }
}

function setEditorStatus(text, isError) {
  const status = document.getElementById("editor-status");
  status.textContent = text || "";
  status.classList.toggle("is-error", Boolean(isError));
}

// Vị trí cột nội dung. API chấp nhận "text_" hoặc "text"; trả -1 nếu không có
// để giao diện cảnh báo trước khi gửi, thay vì để server trả lỗi.
function editorTextColumnIndex() {
  const headers = state.edit.headers;
  for (let i = 0; i < headers.length; i++) {
    const name = headers[i].trim().toLowerCase();
    if (name === "text_" || name === "text") {
      return i;
    }
  }
  return -1;
}

function emptyEditorRow() {
  return state.edit.headers.map(function () {
    return "";
  });
}

function autoGrowTextarea(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = textarea.scrollHeight + "px";
}

function makeEditorHeaderCell(text, className) {
  const cell = document.createElement("th");
  cell.textContent = text;
  if (className) {
    cell.className = className;
  }
  return cell;
}

function renderEditor() {
  const edit = state.edit;
  const head = document.getElementById("editor-head");
  const body = document.getElementById("editor-body");
  const textColumn = editorTextColumnIndex();

  head.innerHTML = "";
  body.innerHTML = "";

  const headRow = document.createElement("tr");
  headRow.appendChild(makeEditorHeaderCell("#", "editor-row-number"));
  for (let column = 0; column < edit.headers.length; column++) {
    headRow.appendChild(makeEditorHeaderCell(edit.headers[column], ""));
  }
  headRow.appendChild(makeEditorHeaderCell("Xoá", "editor-remove-head"));
  head.appendChild(headRow);

  const pageCount = Math.max(1, Math.ceil(edit.rows.length / edit.pageSize));
  edit.page = Math.min(Math.max(1, edit.page), pageCount);
  const start = (edit.page - 1) * edit.pageSize;
  const end = Math.min(start + edit.pageSize, edit.rows.length);

  for (let rowIndex = start; rowIndex < end; rowIndex++) {
    const row = document.createElement("tr");

    const numberCell = document.createElement("td");
    numberCell.className = "editor-row-number";
    numberCell.textContent = String(rowIndex + 1);
    row.appendChild(numberCell);

    for (let column = 0; column < edit.headers.length; column++) {
      const cell = document.createElement("td");
      let control;

      // Cột nội dung dùng textarea để đọc được cả câu dài; các cột khác
      // (số sao, nhóm) chỉ cần một dòng.
      if (column === textColumn) {
        control = document.createElement("textarea");
        control.className = "editor-textarea";
        control.rows = 2;
      } else {
        control = document.createElement("input");
        control.type = "text";
        control.className = "editor-input";
      }

      control.value = edit.rows[rowIndex][column];
      control.dataset.row = String(rowIndex);
      control.dataset.col = String(column);
      control.setAttribute(
        "aria-label",
        (edit.headers[column] || "cột " + (column + 1)) + ", dòng " + (rowIndex + 1)
      );
      cell.appendChild(control);
      row.appendChild(cell);
    }

    const actionCell = document.createElement("td");
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "editor-remove";
    removeButton.textContent = "\u00d7";
    removeButton.title = "Xoá dòng " + (rowIndex + 1);
    removeButton.dataset.row = String(rowIndex);
    actionCell.appendChild(removeButton);
    row.appendChild(actionCell);

    body.appendChild(row);
  }

  const textareas = body.querySelectorAll("textarea");
  for (let i = 0; i < textareas.length; i++) {
    autoGrowTextarea(textareas[i]);
  }

  document.getElementById("editor-count").textContent =
    countText(edit.rows.length) + " dòng · " + edit.headers.length + " cột";
  document.getElementById("editor-page-label").textContent =
    "Trang " + edit.page + "/" + pageCount + " · " + edit.pageSize + " dòng/trang";
  document.getElementById("editor-prev").disabled = edit.page <= 1;
  document.getElementById("editor-next").disabled = edit.page >= pageCount;
  document.getElementById("editor-hint").textContent = textColumn >= 0
    ? "Sửa trực tiếp trong ô. Cột text_ dùng ô nhiều dòng."
    : "Không thấy cột text_ hoặc text — API sẽ từ chối bảng này.";
}

async function loadFileIntoEditor() {
  const input = document.getElementById("csv-file");
  const status = document.getElementById("upload-status");
  const file = input.files[0];

  document.getElementById("upload-warnings").innerHTML = "";
  status.textContent = "";
  setEditorStatus("");

  if (!file) {
    return;
  }

  status.textContent = "Đang đọc file...";
  let text = "";
  try {
    // Vì sao không dùng file.text(): hàm đó giải mã UTF-8 và BỎ BOM, nên
    // csv.js không biết file gốc có BOM để ghi lại. TextDecoder với
    // ignoreBOM:true giữ nguyên ký tự BOM ở đầu chuỗi.
    const buffer = await file.arrayBuffer();
    text = new TextDecoder("utf-8", { ignoreBOM: true }).decode(buffer);
  } catch (error) {
    status.textContent = "";
    showUploadWarnings(["Không đọc được file: " + error], true);
    return;
  } finally {
    // Xoá lựa chọn để chọn lại đúng file đó vẫn kích hoạt sự kiện change.
    input.value = "";
  }

  if (!window.CsvTools) {
    status.textContent = "";
    showUploadWarnings(["Thiếu Web/csv.js nên không đọc được CSV."], true);
    return;
  }

  const parsed = window.CsvTools.parse(text);
  if (parsed.headers.length === 0) {
    status.textContent = "";
    showUploadWarnings(["File CSV không có dòng tiêu đề."], true);
    return;
  }
  if (parsed.rows.length === 0) {
    status.textContent = "";
    showUploadWarnings(["File CSV chỉ có dòng tiêu đề, chưa có dữ liệu."], true);
    return;
  }

  state.edit = {
    loaded: true,
    fileName: file.name,
    headers: parsed.headers,
    rows: parsed.rows,
    hasBom: parsed.hasBom,
    eol: parsed.eol,
    page: 1,
    pageSize: state.edit.pageSize
  };

  // Kết quả của file trước không còn đúng với bảng mới, nên bỏ đi.
  state.uploadData = null;
  state.uploadFileName = "";
  document.getElementById("editor-card").hidden = false;
  switchSource("upload");
  renderEditor();

  status.textContent =
    "Đã nạp " + countText(parsed.rows.length) + " dòng từ " + file.name +
    ". Sửa trực tiếp rồi bấm Chạy phân tích bảng.";
  setEditorStatus(
    editorTextColumnIndex() >= 0
      ? "Sẵn sàng chạy."
      : "Thiếu cột text_ hoặc text nên chưa chạy được.",
    editorTextColumnIndex() < 0
  );

  document.getElementById("editor-card").scrollIntoView({
    behavior: "smooth",
    block: "start"
  });
}

function bindEditor() {
  const body = document.getElementById("editor-body");

  // Gán sự kiện ở thân bảng thay vì từng ô: bảng được vẽ lại sau mỗi lần
  // chuyển trang/xoá dòng, gắn trực tiếp sẽ mất hết.
  body.addEventListener("input", function (event) {
    const control = event.target;
    if (control.dataset.row === undefined || control.dataset.col === undefined) {
      return;
    }
    const row = Number(control.dataset.row);
    const column = Number(control.dataset.col);
    if (!state.edit.rows[row]) {
      return;
    }
    state.edit.rows[row][column] = control.value;
    if (control.tagName === "TEXTAREA") {
      autoGrowTextarea(control);
    }
  });

  body.addEventListener("click", function (event) {
    const button = event.target.closest(".editor-remove");
    if (!button) {
      return;
    }
    state.edit.rows.splice(Number(button.dataset.row), 1);
    if (state.edit.rows.length === 0) {
      state.edit.rows.push(emptyEditorRow());
    }
    renderEditor();
  });

  document.getElementById("editor-prev").addEventListener("click", function () {
    state.edit.page = state.edit.page - 1;
    renderEditor();
  });

  document.getElementById("editor-next").addEventListener("click", function () {
    state.edit.page = state.edit.page + 1;
    renderEditor();
  });

  document.getElementById("editor-add").addEventListener("click", function () {
    state.edit.rows.push(emptyEditorRow());
    state.edit.page = Math.ceil(state.edit.rows.length / state.edit.pageSize);
    renderEditor();

    // Đưa con trỏ vào ô đầu của dòng vừa thêm để gõ tiếp ngay.
    const rows = document.querySelectorAll("#editor-body tr");
    if (rows.length > 0) {
      const firstInput = rows[rows.length - 1].querySelector("input, textarea");
      if (firstInput) {
        firstInput.focus();
      }
    }
  });

  document.getElementById("editor-run").addEventListener("click", handleRunEditedTable);
  document.getElementById("editor-save").addEventListener("click", openSaveDialog);
}

// Bỏ các dòng hoàn toàn trống (do bấm "+ Thêm dòng" rồi để không), tránh
// việc API báo "đã bỏ qua N dòng" gây khó hiểu.
function editorRowsForExport() {
  return state.edit.rows.filter(function (row) {
    return row.some(function (value) {
      return String(value).trim() !== "";
    });
  });
}

function buildEditedCsv() {
  return window.CsvTools.serialize(
    state.edit.headers,
    editorRowsForExport(),
    { bom: state.edit.hasBom, eol: state.edit.eol }
  );
}

function handleRunEditedTable() {
  if (!state.edit.loaded) {
    return;
  }

  const textColumn = editorTextColumnIndex();
  if (textColumn < 0) {
    setEditorStatus("Bảng phải có cột text_ hoặc text thì API mới đọc được.", true);
    return;
  }

  const rows = editorRowsForExport();
  const hasText = rows.some(function (row) {
    return String(row[textColumn] || "").trim() !== "";
  });
  if (!hasText) {
    setEditorStatus("Chưa có dòng nào có nội dung ở cột text_.", true);
    return;
  }

  setEditorStatus("");
  runUploadAnalysis(
    buildEditedCsv(),
    state.edit.fileName || "du-lieu-chinh-sua.csv"
  );
}

function uploadPhases(translateRows) {
  if (translateRows) {
    return [
      ["Đang dịch sang tiếng Anh", "Mỗi dòng chưa có trong bộ nhớ đệm tốn khoảng 0,4 giây."],
      ["Đang dự đoán xác suất", "Vectorizer TF-IDF và Logistic Regression chấm từng dòng."],
      ["Đang xếp nhóm và gắn cờ", "Áp ngưỡng, luật số từ, trùng lặp và số sao."],
      ["Đang tổng hợp số liệu", "Đếm nhóm, dựng bảng 5 sao và danh sách review."]
    ];
  }
  return [
    ["Đang gửi dữ liệu tới model", "Bỏ qua bước dịch nên kết quả tiếng Việt có thể kém chính xác."],
    ["Đang dự đoán xác suất", "Vectorizer TF-IDF và Logistic Regression chấm từng dòng."],
    ["Đang xếp nhóm và gắn cờ", "Áp ngưỡng, luật số từ, trùng lặp và số sao."],
    ["Đang tổng hợp số liệu", "Đếm nhóm, dựng bảng 5 sao và danh sách review."]
  ];
}

// API trả kết quả một lần, nên sau khi có response mới ghi đủ 4 dòng kết quả
// cuối cùng. Màn hình chờ được giữ thêm UPLOAD_RESULT_HOLD_MS để đọc kịp.
function logUploadResults(data, translateRows) {
  const rows = Array.isArray(data.rows) ? data.rows : [];

  if (translateRows) {
    let translated = 0;
    for (let i = 0; i < rows.length; i++) {
      if (rows[i].used_translation) {
        translated += 1;
      }
    }
    completeLoaderStep(
      data.meta.translation_cutoff
        ? "Dịch sang tiếng Anh (hết giới hạn)"
        : "Dịch sang tiếng Anh",
      countText(translated) + " dòng đã dịch · " +
      countText(rows.length - translated) + " dòng giữ nguyên"
    );
  } else {
    completeLoaderStep(
      "Gửi dữ liệu tới model",
      countText(data.meta.analyzed_rows) + " dòng đã nhận"
    );
  }

  const range = loaderProbabilityRange(rows);
  completeLoaderStep(
    "Dự đoán xác suất",
    "Ngưỡng " + Number(data.meta.threshold).toFixed(2) +
    (range ? " · xác suất Giả " + range : "")
  );

  completeLoaderStep(
    "Xếp nhóm và gắn cờ",
    loaderCategorySummary(data.summary.categories)
  );

  completeLoaderStep(
    "Tổng hợp số liệu",
    countText(data.summary.useful_count) + " hữu ích · 5 nhóm · bảng 5 sao"
  );
}

async function runUploadAnalysis(csvText, fileName) {
  const translateRows = document.getElementById("translate-upload").checked;
  const demoMeta = state.demoData ? state.demoData.meta : null;
  const translateSeconds = demoMeta && demoMeta.max_upload_translate_seconds
    ? demoMeta.max_upload_translate_seconds
    : 300;

  const phases = uploadPhases(translateRows);
  let phaseIndex = 0;
  const numberStarts = captureNumberStarts();
  let uploadRushPlan = {};
  showLoader(phases[0][0], phases[0][1], {
    limitSeconds: translateRows ? translateSeconds : 0
  });

  const phaseTimer = window.setInterval(function () {
    phaseIndex = Math.min(phaseIndex + 1, phases.length - 1);
    setLoaderText(phases[phaseIndex][0], phases[phaseIndex][1]);
  }, UPLOAD_PHASE_MS);

  const runButton = document.getElementById("editor-run");
  const headerRun = document.getElementById("train-button");
  runButton.disabled = true;
  // Khoá nút chạy của header trong lúc chờ API thay vì ẩn đi: bấm vào lúc này
  // sẽ khởi động chuỗi demo song song, nhưng ẩn nút sẽ làm dãy nút đầu trang
  // co lại và đẩy công tắc nền tối sang trái.
  if (headerRun) {
    headerRun.disabled = true;
  }
  setEditorStatus("");

  try {
    const response = await fetch("/api/analyze-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        csv_text: csvText,
        translate: translateRows,
        file_name: fileName
      })
    });

    const data = await response.json();
    window.clearInterval(phaseTimer);
    if (loaderState.cancelled) {
      throw CANCEL_SENTINEL;
    }

    if (!response.ok) {
      setEditorStatus(data.error || "API trả về lỗi.", true);
      return;
    }

    state.uploadData = data;
    state.uploadFileName = fileName;
    switchSource("upload");
    loading_skeleton(true, { starts: numberStarts });

    setEditorStatus(
      "Xong: " + countText(data.meta.analyzed_rows) + " dòng trong " +
      data.meta.elapsed_seconds + " giây."
    );
    showUploadWarnings(data.warnings || [], false);

    logUploadResults(data, translateRows);
    setLoaderText(
      "Hoàn tất phân tích",
      "Đã xếp nhóm " + countText(data.meta.analyzed_rows) + " dòng."
    );
      uploadRushPlan = collectSkeletonRushPlan();
    await pause(UPLOAD_RESULT_HOLD_MS);

    document.getElementById("summary-card").scrollIntoView({
      behavior: "smooth",
      block: "start"
    });
  } catch (error) {
    if (error === CANCEL_SENTINEL) {
      setEditorStatus("Đã huỷ quá trình. Dữ liệu preview giữ nguyên.");
      return;
    }
    setEditorStatus(
      "Không gọi được API. Hãy chạy: python MaNGuon/api_server.py rồi mở " +
      "http://127.0.0.1:8000/ (không double-click file).",
      true
    );
  } finally {
    window.clearInterval(phaseTimer);
    hideLoader();
    applyRushPlan(uploadRushPlan);
    runButton.disabled = false;
    if (headerRun) {
      headerRun.disabled = false;
    }
  }
}

/* ============================================================
   Hỏi nơi lưu CSV: ghi đè file gốc hay tải bản riêng
   ============================================================ */

// File System Access API chỉ có trên trình duyệt nhân Chromium và chỉ chạy
// trong ngữ cảnh bảo mật (http://127.0.0.1 được tính là bảo mật, file:// thì
// không). Thiếu API thì vẫn tải bản sao bình thường.
function canWriteFiles() {
  return typeof window.showSaveFilePicker === "function" &&
    window.isSecureContext === true;
}

function openSaveDialog() {
  if (!state.edit.loaded) {
    return;
  }

  const dialog = document.getElementById("save-dialog");
  const overwrite = document.getElementById("save-overwrite");
  const note = document.getElementById("save-overwrite-note");
  const writeAllowed = canWriteFiles();

  overwrite.disabled = !writeAllowed;
  note.textContent = writeAllowed
    ? "Trình duyệt sẽ hỏi quyền ghi và bạn chọn lại đúng file CSV gốc."
    : "Chỉ dùng được khi mở qua http://127.0.0.1:8000/ trên Chrome hoặc Edge.";

  document.getElementById("save-dialog-text").textContent =
    "Bảng có " + countText(editorRowsForExport().length) + " dòng và " +
    state.edit.headers.length + " cột. Chọn cách lưu:";

  dialog.classList.add("is-open");
  (writeAllowed ? overwrite : document.getElementById("save-copy")).focus();
}

function closeSaveDialog() {
  document.getElementById("save-dialog").classList.remove("is-open");
  const saveButton = document.getElementById("editor-save");
  if (saveButton) {
    saveButton.focus();
  }
}

function csvCopyName(name) {
  const base = String(name || "du-lieu").replace(/\.csv$/i, "");
  return base + "_da-sua.csv";
}

function downloadCsvText(csvText, fileName) {
  // Kiểu MIME chỉ để trình duyệt biết đây là CSV. BOM UTF-8 (nếu file gốc có)
  // đã nằm sẵn trong csvText do buildEditedCsv() giữ lại.
  const blob = new Blob([csvText], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(function () {
    URL.revokeObjectURL(url);
  }, 1000);
}

function saveAsCopy() {
  const fileName = csvCopyName(state.edit.fileName);
  downloadCsvText(buildEditedCsv(), fileName);
  closeSaveDialog();
  setEditorStatus("Đã tải bản CSV riêng: " + fileName);
}

async function saveOverwrite() {
  const csvText = buildEditedCsv();
  closeSaveDialog();

  if (!canWriteFiles()) {
    setEditorStatus(
      "Trình duyệt này không cho ghi đè file. Hãy dùng Tải thành bản CSV riêng.",
      true
    );
    return;
  }

  try {
    // Hộp thoại của trình duyệt chính là bước xin quyền: người dùng chọn file,
    // nếu file đã tồn tại thì trình duyệt hỏi lại trước khi ghi đè.
    const handle = await window.showSaveFilePicker({
      suggestedName: state.edit.fileName || "du-lieu.csv",
      types: [{ description: "CSV", accept: { "text/csv": [".csv"] } }]
    });
    const writable = await handle.createWritable();
    await writable.write(csvText);
    await writable.close();
    setEditorStatus("Đã ghi đè file: " + handle.name + ".");
  } catch (error) {
    if (error && error.name === "AbortError") {
      setEditorStatus("Đã huỷ lưu file.");
      return;
    }
    setEditorStatus("Không ghi được file: " + error, true);
  }
}

function bindSaveDialog() {
  const dialog = document.getElementById("save-dialog");

  document.getElementById("save-cancel").addEventListener("click", closeSaveDialog);
  document.getElementById("save-copy").addEventListener("click", saveAsCopy);
  document.getElementById("save-overwrite").addEventListener("click", saveOverwrite);

  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) {
      closeSaveDialog();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && dialog.classList.contains("is-open")) {
      closeSaveDialog();
    }
  });
}

/* ============================================================
   Nhập review và gọi API
   ============================================================ */

// Các câu mẫu để người xem bấm thử nhanh. Phần lớn là tiếng Anh (đúng miền
// dữ liệu huấn luyện); riêng nút tiếng Việt để thử bước dịch tự động.
const EXAMPLE_REVIEWS = [
  {
    name: "Máy sinh 1",
    text: "This product is absolutely amazing! I have never seen anything like it before. It exceeded all my expectations and I would recommend it to everyone. Five stars!"
  },
  {
    name: "Máy sinh 2",
    text: "Great quality and fast shipping. The seller is very professional and the item is exactly as described. I am completely satisfied with my purchase and will buy again."
  },
  {
    name: "Máy sinh 3",
    text: "Best purchase I have ever made. The price is unbeatable and the quality is outstanding. Do not hesitate, just buy it now. You will not regret it."
  },
  {
    name: "Người viết 1",
    text: "Bought this for my sister's birthday last week. The box arrived dented on one corner, but the blender itself worked fine. It is louder than I expected, though it crushes ice without any problem. Three weeks in, no issues."
  },
  {
    name: "Người viết 2",
    text: "I have used this keyboard for about two months now, typing roughly six hours a day. The spacebar started squeaking after the first month, which is annoying, but the switches still feel consistent. Battery lasts around nine days with backlight off."
  },
  {
    name: "Người viết 3",
    text: "Ordered the blue version, size medium. It fits well around the shoulders but the sleeves are a bit long for me, so I rolled them up. The fabric is thinner than the photos suggest. Overall okay for the price, not amazing."
  },
  {
    name: "Bẫy: quá ngắn",
    text: "Good product, works fine."
  },
  {
    name: "Bẫy: khen kiểu người",
    text: "I bought this and it changed my life, best thing ever, my whole family loves it."
  },
  {
    name: "Tiếng Việt (qua dịch)",
    text: "Sản phẩm này rất tốt, tôi rất hài lòng và sẽ mua lại."
  }
];

function renderExampleButtons() {
  const container = document.getElementById("example-buttons");
  const input = document.getElementById("review-input");

  for (let i = 0; i < EXAMPLE_REVIEWS.length; i++) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "example-button";
    button.textContent = EXAMPLE_REVIEWS[i].name;

    button.addEventListener("click", function () {
      input.value = EXAMPLE_REVIEWS[i].text;
      input.focus();
    });

    container.appendChild(button);
  }
}

function showPredictError(message) {
  const box = document.getElementById("predict-result");
  box.innerHTML = "";

  const warning = createDiv("predict-warning");
  warning.textContent = message;
  box.appendChild(warning);
}

function showPredictResult(result) {
  const box = document.getElementById("predict-result");
  box.innerHTML = "";

  const categoryId = result.category
    ? result.category
    : (result.label === 1 ? "suspected_fake" : "genuine");
  const isFake = result.label === 1;

  // Dòng 1: con số xác suất Giả, cỡ lớn.
  const headline = createDiv("predict-headline");
  headline.appendChild(createDiv("predict-value", percentText(result.probability_fake)));
  headline.appendChild(createDiv("predict-caption", "xác suất là review Giả"));
  box.appendChild(headline);

  // Dòng 2: thanh trực quan.
  const bar = createDiv("predict-bar");
  const fill = createDiv(isFake ? "predict-fill is-fake" : "predict-fill is-real");
  fill.style.width = Math.min(100, result.probability_fake * 100) + "%";
  bar.appendChild(fill);
  box.appendChild(bar);

  // Dòng 3: nhóm hiển thị + cơ sở + có được giữ lại hay không.
  const verdict = createDiv("predict-verdict");
  verdict.appendChild(makeCategoryTag(categoryId));

  const predictBasis = result.category_basis
    ? result.category_basis
    : basisForCategory(categoryId);
  verdict.appendChild(makeBasisTag(predictBasis));

  verdict.appendChild(
    document.createTextNode(
      result.is_useful ? " · được giữ lại" : " · không hữu ích, sẽ bị loại"
    )
  );
  box.appendChild(verdict);

  // Lý do xếp nhóm, hiện ngay dưới kết luận.
  if (result.reasons && result.reasons.length > 0) {
    const reasonsList = document.createElement("ul");
    reasonsList.className = "reasons-list predict-reasons";
    for (let i = 0; i < result.reasons.length; i++) {
      const item = document.createElement("li");
      item.textContent = result.reasons[i];
      reasonsList.appendChild(item);
    }
    box.appendChild(reasonsList);
  }

  // Dòng 4: thông tin phụ, gồm tỷ lệ từ quen.
  const details = createDiv("predict-details");
  const ratioPercent = result.known_token_ratio === undefined
    ? "?"
    : (result.known_token_ratio * 100).toFixed(1) + "%";
  details.textContent =
    "Xác suất Thật: " +
    percentText(result.probability_real) +
    " - Từ/cụm từ có trong từ vựng model: " +
    result.known_token_count +
    "/" +
    result.token_count +
    " (" + ratioPercent + ")" +
    " - Số từ: " +
    (result.word_count === undefined ? "?" : result.word_count);
  box.appendChild(details);

  // Dòng 5: bản dịch mà model thực sự đọc.
  if (result.used_translation) {
    const note = createDiv("predict-note");
    note.appendChild(createDiv("predict-note-label", "Bản dịch model đã đọc:"));
    note.appendChild(createDiv("predict-note-text", result.translated_text));

    // Nhà cung cấp dịch và ngôn ngữ nhận diện giúp chẩn đoán khi bản dịch sai.
    const providerParts = [];
    if (result.translation_provider) {
      providerParts.push("nguồn dịch: " + result.translation_provider);
    }
    if (result.detected_language) {
      providerParts.push("ngôn ngữ nhận diện: " + result.detected_language);
    }
    if (providerParts.length > 0) {
      note.appendChild(createDiv("predict-note-meta", providerParts.join(" · ")));
    }
    box.appendChild(note);

    const translateWarning = createDiv("predict-warning is-soft");
    translateWarning.textContent =
      "Câu này đã qua dịch máy. Văn bản dịch mang đặc điểm 'máy sinh', nên " +
      "xác suất Giả có xu hướng cao hơn thực tế. Hãy đọc bản dịch ở trên để " +
      "tự đánh giá.";
    box.appendChild(translateWarning);

    // Hai cờ dưới đây giải thích vì sao kết luận có thể không ổn định.
    if (result.translation_borderline) {
      const borderline = createDiv("predict-warning");
      borderline.textContent =
        "CẢNH BÁO: xác suất nằm sát ngưỡng quyết định, chỉ cần bản dịch khác " +
        "một chút là kết luận có thể đổi. Review này không được giữ lại.";
      box.appendChild(borderline);
    }

    if (result.translation_inconsistent) {
      const similarity = result.translation_similarity === null ||
        result.translation_similarity === undefined
        ? "?"
        : (result.translation_similarity * 100).toFixed(1) + "%";
      const inconsistent = createDiv("predict-warning");
      inconsistent.textContent =
        "CẢNH BÁO: dịch vòng (gốc -> Anh -> gốc) chỉ khớp " + similarity +
        " so với câu gốc, nên bản dịch có thể đã làm sai nghĩa. " +
        "Review này không được giữ lại.";
      box.appendChild(inconsistent);
    }
  }

  if (result.translation_error) {
    const translateError = createDiv("predict-warning");
    translateError.textContent =
      result.translation_error + " - đang dự đoán trên câu gốc.";
    box.appendChild(translateError);
  }

  // Cảnh báo khi câu gần như không có từ nào model từng thấy.
  if (!result.is_reliable) {
    const warning = createDiv("predict-warning");
    warning.textContent =
      "CẢNH BÁO: câu này gần như không có từ nào nằm trong từ vựng model " +
      "(model chỉ học review tiếng Anh). Con số phía trên KHÔNG có ý nghĩa.";
    box.appendChild(warning);
  }
}

async function handlePredict() {
  const input = document.getElementById("review-input");
  const status = document.getElementById("predict-status");

  const text = input.value.trim();
  document.getElementById("predict-result").innerHTML = "";

  if (!text) {
    status.textContent = "Hãy nhập nội dung review trước.";
    return;
  }

  status.textContent = "Đang phân tích...";

  try {
    const response = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text })
    });

    const data = await response.json();

    if (!response.ok) {
      status.textContent = "";
      showPredictError(data.error || "API trả về lỗi.");
      return;
    }

    status.textContent = "";
    showPredictResult(data);
  } catch (error) {
    status.textContent = "";
    showPredictError(
      "Không gọi được API. Hãy chạy: python MaNguon/api_server.py " +
        "rồi mở http://127.0.0.1:8000/ (không double-click file)."
    );
  }
}

/* ============================================================
   Tương tác sống động: sóng nước khi bấm chỗ trống
   ============================================================ */

const liveEffects = { lastRippleAt: 0, active: 0, max: 24 };

// Các điều khiển đã tự có phản hồi nén lò xo qua CSS :active. Chỉ tạo ripple
// khi bấm vào nền trống, và bỏ qua chữ đang chọn để không cản copy/paste.
function isLiveControl(target) {
  return Boolean(target && target.closest &&
    target.closest(
      "button, a, input, textarea, select, label, summary, " +
      "[role='button'], .category-card, .kpi, .preview-card"
    ));
}

function isPlainTextTarget(target) {
  return Boolean(
    target && target.children.length === 0 &&
    target.textContent && target.textContent.trim()
  );
}

function trackLiveEffect(node) {
  liveEffects.active++;
  node.addEventListener("animationend", function () {
    node.remove();
    liveEffects.active = Math.max(0, liveEffects.active - 1);
  }, { once: true });
}

function spawnLiveRipple(event) {
  if (reducedMotionEnabled()) {
    return;
  }
  const now = Date.now();
  if (now - liveEffects.lastRippleAt < 70 ||
      liveEffects.active >= liveEffects.max) {
    return;
  }
  liveEffects.lastRippleAt = now;

  const x = event.clientX;
  const y = event.clientY;
  const ripple = document.createElement("span");
  ripple.className = "live-ripple";
  ripple.style.setProperty("--x", x + "px");
  ripple.style.setProperty("--y", y + "px");
  document.body.appendChild(ripple);
  trackLiveEffect(ripple);

  const sparks = 5;
  for (let i = 0; i < sparks; i++) {
    const angle = (Math.PI * 2 * i) / sparks + (Math.random() - 0.5) * 0.5;
    const distance = 18 + Math.random() * 16;
    const spark = document.createElement("span");
    spark.className = "live-particle";
    spark.style.setProperty("--x", x + "px");
    spark.style.setProperty("--y", y + "px");
    spark.style.setProperty("--dx", Math.cos(angle) * distance + "px");
    spark.style.setProperty("--dy", Math.sin(angle) * distance + "px");
    document.body.appendChild(spark);
    trackLiveEffect(spark);
  }
}

function bindLiveInteractions() {
  document.addEventListener("pointerdown", function (event) {
    if (!event.isPrimary || event.button !== 0) {
      return;
    }
    if (isLiveControl(event.target) || isPlainTextTarget(event.target)) {
      return;
    }
    spawnLiveRipple(event);
  });
}

function bindTableSearch() {
  const input = document.getElementById("table-search");
  if (!input) {
    return;
  }
  input.addEventListener("input", function () {
    setQuery(input.value);
  });
}

/* ============================================================
   Phân trang
   ============================================================ */

function bindPagination() {
  document.getElementById("page-first").addEventListener("click", function () {
    state.currentPage = 1;
    renderTable();
  });

  document.getElementById("page-prev").addEventListener("click", function () {
    state.currentPage = state.currentPage - 1;
    renderTable();
  });

  document.getElementById("page-next").addEventListener("click", function () {
    state.currentPage = state.currentPage + 1;
    renderTable();
  });

  document.getElementById("page-last").addEventListener("click", function () {
    state.currentPage = totalPageCount(getVisibleRows().length);
    renderTable();
  });
}

/* ============================================================
   Nạp dữ liệu review và trạng thái bảng
   ============================================================ */

// Nạp data_reviews.js bằng thẻ <script> chèn vào trang.
// Vì sao không dùng fetch(): mở bằng double-click là giao thức file://,
// trình duyệt chặn fetch() vì CORS, còn thẻ script thì vẫn nạp được.
// onDone luôn được gọi, kể cả khi lỗi, để trang không bị treo ở trạng thái chờ.
function loadReviewsScript(onDone) {
  if (Array.isArray(window.WEB_DATA_REVIEWS)) {
    onDone();
    return;
  }

  const script = document.createElement("script");
  // Dữ liệu review nằm trong DuLieuDemo/ (ngang cấp Web/), không cùng thư mục
  // với app.js. Dùng ../ để đúng cả khi mở file:// lẫn khi chạy qua API server.
  script.src = "../DuLieuDemo/data_reviews.js";
  script.onload = onDone;
  script.onerror = onDone;
  document.body.appendChild(script);
}

// Bọc loadReviewsScript thành Promise và chỉ nạp một lần. Nhờ vậy bấm
// "Chạy lại quá trình" không tải lại file 4,3 MB từ ổ đĩa.
let demoReviewsPending = null;

function ensureDemoReviews() {
  if (Array.isArray(window.WEB_DATA_REVIEWS) && window.WEB_DATA_REVIEWS.length > 0) {
    return Promise.resolve(window.WEB_DATA_REVIEWS);
  }
  if (demoReviewsPending === null) {
    demoReviewsPending = new Promise(function (resolve) {
      loadReviewsScript(function () {
        resolve(Array.isArray(window.WEB_DATA_REVIEWS) ? window.WEB_DATA_REVIEWS : null);
      });
    });
  }
  return demoReviewsPending;
}

// Hiện một dòng thông báo trong thân bảng, dùng khi dữ liệu chưa nạp xong.
// Vì sao cần: bảng trống dễ bị hiểu là "không có review nào khớp".
function setTableMessage(text, isError) {
  const body = document.getElementById("table-body");
  body.innerHTML = "";

  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 10;
  cell.className = isError ? "table-message is-error" : "table-message";
  cell.textContent = text;
  row.appendChild(cell);
  body.appendChild(row);
}

/* ============================================================
   Đèn báo kết nối PostgreSQL
   ============================================================ */

// Đèn chỉ có nghĩa khi trang chạy qua api_server.py (giao thức http://).
// Mở bằng file:// thì fetch() bị chặn, nên báo "không có server" thay vì
// báo nhầm là database hỏng.
const HEALTH_ENDPOINT = "/api/health";

// 10 giây đủ nhanh để thấy DB vừa tắt, mà không gọi mạng quá nhiều.
const HEALTH_POLL_INTERVAL_MS = 10000;

// Cập nhật pill. Tách riêng để mọi nhánh (kể cả lỗi) chỉ có một chỗ sửa giao diện.
function setDbStatus(statusId, text, title) {
  const pill = document.getElementById("db-status");

  // Bản HTML cũ không có pill: bỏ qua thay vì làm vỡ cả trang.
  if (!pill) {
    return;
  }

  pill.dataset.state = statusId;
  pill.title = title;
  document.getElementById("db-status-text").textContent = text;
}

async function checkDatabaseHealth() {
  if (window.location.protocol === "file:") {
    setDbStatus(
      "offline",
      "Không có server",
      "Trang đang mở bằng file://. Chạy python MaNguon/api_server.py để dùng đèn báo này."
    );
    return;
  }

  try {
    // cache: "no-store" để trình duyệt không dùng lại kết quả cũ.
    // AbortSignal.timeout(5000): nếu server treo, đèn không bị kẹt ở trạng thái cũ.
    const response = await fetch(HEALTH_ENDPOINT, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000)
    });
    const payload = await response.json();

    if (payload.database) {
      setDbStatus(
        "connected",
        "CSDL đã kết nối",
        "PostgreSQL phản hồi trong " + payload.latency_ms + " ms (lúc " +
          payload.checked_at + ")."
      );
    } else {
      // API còn sống nhưng không nối được PostgreSQL: đây mới là "mất CSDL".
      setDbStatus(
        "disconnected",
        "Mất kết nối CSDL",
        "API vẫn chạy nhưng không kết nối được PostgreSQL. " +
          "Chạy ThuMucKhoiChay\\4_Chay_Tat_Ca.bat."
      );
    }
  } catch {
    // Không gọi được /api/health: server chưa chạy, sai cổng, hoặc quá 5 giây.
    setDbStatus(
      "offline",
      "Không có server",
      "Không gọi được /api/health. Chạy python MaNguon/api_server.py."
    );
  }
}

function startDbHealthPolling() {
  checkDatabaseHealth();

  setInterval(function () {
    // Tab đang bị ẩn thì bỏ lượt này: không ai nhìn đèn, gọi mạng là vô ích.
    if (document.hidden) {
      return;
    }
    checkDatabaseHealth();
  }, HEALTH_POLL_INTERVAL_MS);

  // Quay lại tab thì kiểm tra ngay, không phải chờ hết chu kỳ 10 giây.
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      checkDatabaseHealth();
    }
  });
}

/* ============================================================
   Khởi động
   ============================================================ */

/* ============================================================
   Bảng demo: mở bằng nút, lọc và nạp dần khi cuộn
   ============================================================ */

function previewReviewValues(review) {
  return [
    review.row_index,
    shortText(review.text, 110),
    review.rating,
    review.true_label === 1 ? "Giả" : "Thật",
    percentText(review.prob_fake),
    categoryInfo(review.category).label
  ];
}

function filteredDemoReviews() {
  const query = foldForSearch(demoPreview.query).text;
  return demoPreview.reviews.filter(function (review) {
    if (demoPreview.star !== "all" &&
        Math.round(Number(review.rating) || 0) !== Number(demoPreview.star)) {
      return false;
    }
    if (demoPreview.label !== "all") {
      const isFake = review.true_label === 1;
      if ((demoPreview.label === "fake") !== isFake) {
        return false;
      }
    }
    if (demoPreview.category !== "all" && review.category !== demoPreview.category) {
      return false;
    }
    if (query && foldForSearch(review.text).text.indexOf(query) === -1) {
      return false;
    }
    return true;
  });
}

function renderDemoPreviewTable() {
  const body = document.getElementById("preview-body");
  const wrap = document.getElementById("preview-table-wrap");
  if (!body || !wrap) {
    return;
  }

  const matched = filteredDemoReviews();
  const rows = matched.map(previewReviewValues);
  const count = document.getElementById("preview-filter-count");
  if (count) {
    const hasFilter = Boolean(demoPreview.query) || demoPreview.star !== "all" ||
      demoPreview.label !== "all" || demoPreview.category !== "all";
    count.textContent = "Khớp " + countText(rows.length) + " / " +
      countText(demoPreview.reviews.length) + " review" +
      (hasFilter ? " · đang lọc" : "");
  }

  bindInfiniteTable(body, wrap, {
    rows: rows,
    query: demoPreview.query,
    status: document.getElementById("preview-table-status"),
    totalText: countText(rows.length) + " review khớp"
  });
}

function syncPreviewFilterChips() {
  const chips = document.querySelectorAll("#preview-filter-chips .preview-filter-chip");
  for (let i = 0; i < chips.length; i++) {
    const chip = chips[i];
    const active = demoPreview[chip.dataset.filterKey] === chip.dataset.filterValue;
    chip.classList.toggle("is-active", active);
    chip.setAttribute("aria-pressed", active ? "true" : "false");
  }
}

function buildPreviewFilterChips() {
  const host = document.getElementById("preview-filter-chips");
  if (!host) {
    return;
  }
  host.replaceChildren();

  const categoryItems = [["all", "Tất cả"]].concat(CATEGORY_ORDER.map(function (id) {
    return [id, categoryInfo(id).label];
  }));
  const groups = [
    { key: "star", label: "Sao", items: [
      ["all", "Tất cả"], ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]
    ]},
    { key: "label", label: "Nhãn", items: [
      ["all", "Tất cả"], ["real", "Thật"], ["fake", "Giả"]
    ]},
    { key: "category", label: "Nhóm", items: categoryItems }
  ];

  groups.forEach(function (group) {
    const wrap = createDiv("preview-filter-group");
    wrap.appendChild(createDiv("preview-filter-group-label", group.label));
    group.items.forEach(function (item) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "preview-filter-chip";
      chip.textContent = item[1];
      chip.dataset.filterKey = group.key;
      chip.dataset.filterValue = item[0];
      chip.addEventListener("click", function () {
        demoPreview[group.key] = item[0];
        syncPreviewFilterChips();
        if (demoPreview.open) {
          renderDemoPreviewTable();
        }
      });
      wrap.appendChild(chip);
    });
    host.appendChild(wrap);
  });
  syncPreviewFilterChips();
}

function toggleDemoPreview() {
  const button = document.getElementById("preview-toggle");
  const panel = document.getElementById("preview-panel");
  if (!button || !panel) {
    return;
  }
  demoPreview.open = !demoPreview.open;
  panel.hidden = !demoPreview.open;
  button.setAttribute("aria-expanded", demoPreview.open ? "true" : "false");
  button.textContent = demoPreview.open ? "Ẩn preview dữ liệu" : "Xem preview dữ liệu";
  if (demoPreview.open && demoPreview.reviews.length > 0) {
    renderDemoPreviewTable();
  }
}

function bindDemoPreview() {
  const toggle = document.getElementById("preview-toggle");
  const search = document.getElementById("preview-search");
  const reset = document.getElementById("preview-filter-reset");

  if (toggle) {
    toggle.addEventListener("click", toggleDemoPreview);
  }
  if (search) {
    let debounceId = 0;
    search.addEventListener("input", function () {
      window.clearTimeout(debounceId);
      debounceId = window.setTimeout(function () {
        demoPreview.query = search.value.trim();
        if (demoPreview.open) {
          renderDemoPreviewTable();
        }
      }, 150);
    });
  }
  if (reset) {
    reset.addEventListener("click", function () {
      demoPreview.query = "";
      demoPreview.star = "all";
      demoPreview.label = "all";
      demoPreview.category = "all";
      if (search) {
        search.value = "";
      }
      syncPreviewFilterChips();
      if (demoPreview.open) {
        renderDemoPreviewTable();
      }
    });
  }
  buildPreviewFilterChips();
}

// Mở trang chỉ xem trước dữ liệu: nạp data_reviews.js và để đó, bảng chỉ dựng
// khi người xem bấm nút. Không gọi runProcessingSequence() ở đây.
async function preparePreview() {
  const count = document.getElementById("preview-count");
  const status = document.getElementById("preview-status");
  if (status) {
    status.textContent = "Đang nạp review từ DuLieuDemo/data_reviews.js...";
  }

  const reviews = await ensureDemoReviews();
  if (!Array.isArray(reviews) || reviews.length === 0) {
    if (status) {
      status.textContent = "Không nạp được dữ liệu. Hãy chạy python MaNguon\\export_web_data.py";
    }
    return false;
  }

  demoPreview.reviews = reviews;
  if (state.demoData) {
    state.demoData.reviews = reviews;
  }
  if (count) {
    // Chỉ phần số nằm trong span riêng: loading_skeleton() và hiệu ứng tăng
    // tốc vì thế không làm mờ hay làm nhấp nháy chữ "review".
    const number = document.createElement("span");
    number.className = "preview-count-number";
    number.textContent = countText(reviews.length);
    count.replaceChildren(number, document.createTextNode(" review"));
  }

  if (status) {
    status.textContent = "Đã nạp " + countText(reviews.length) +
      " review. Bấm “Xem preview dữ liệu” để mở bảng.";
  }
  if (demoPreview.open) {
    renderDemoPreviewTable();
  }
  return true;
}

function showMissingDataError() {
  const main = document.getElementById("app");

  const card = createDiv("card error");
  const title = document.createElement("h2");
  title.textContent = "Chưa có dữ liệu demo";

  const paragraph = document.createElement("p");
  paragraph.appendChild(document.createTextNode("Hãy chạy "));
  const code = document.createElement("code");
  code.textContent = "python MaNguon\\export_web_data.py";
  paragraph.appendChild(code);
  paragraph.appendChild(
    document.createTextNode(
      " để sinh DuLieuDemo/data_meta.js và DuLieuDemo/data_reviews.js, rồi tải lại trang."
    )
  );

  card.appendChild(title);
  card.appendChild(paragraph);

  const summaryCard = document.getElementById("summary-card");
  main.insertBefore(card, summaryCard);
}

// Đọc các thiết lập hiển thị từ meta do Python xuất.
// Vì sao gom vào một hàm: phần khởi động chỉ nên lo nạp dữ liệu và bật sự kiện.
function applyMetaSettings(metaData) {
  const meta = metaData.meta;

  if (meta.sample_page_size) {
    state.pageSize = meta.sample_page_size;
  }

  // Đồng bộ thứ tự nhóm, mẫu câu lý do và nhãn cơ sở với MaNguon/config.py
  // và MaNguon/classify.py để chỉ có một nguồn sự thật.
  if (Array.isArray(meta.category_order) && meta.category_order.length > 0) {
    CATEGORY_ORDER = meta.category_order;
  }
  if (meta.reason_templates) {
    REASON_TEMPLATES = meta.reason_templates;
  }
  if (meta.basis_labels) {
    BASIS_LABELS = meta.basis_labels;
  }

  if (meta.min_useful_words) {
    CATEGORY_INFO.low_content.description =
      "Dưới " + meta.min_useful_words + " từ, không đủ thông tin";
  }
  if (meta.bot_max_words) {
    CATEGORY_INFO.suspected_bot_boost.description =
      "Máy sinh + 5 sao + không quá " + meta.bot_max_words + " từ";
  }

  const maxRows = meta.max_upload_rows || 1000;
  document.getElementById("upload-limit").textContent =
    "Giới hạn: tối đa " + maxRows + " dòng mỗi file, không giới hạn dung lượng.";
}

document.addEventListener("DOMContentLoaded", function () {
  // Chế độ sáng/tối phải áp dụng trước khi vẽ bất cứ thứ gì, để biểu đồ
  // lấy đúng bảng màu ngay từ lần vẽ đầu tiên.
  initTheme();
  initMenu();

  // Đèn báo CSDL chạy độc lập với dữ liệu demo, nên bật trước mọi thứ khác.
  startDbHealthPolling();

  // Khối nhập tay hoạt động độc lập với dữ liệu demo, nên khởi tạo trước.
  renderExampleButtons();
  document.getElementById("predict-button").addEventListener("click", handlePredict);

  document.getElementById("tab-demo").addEventListener("click", function () {
    switchSource("demo");
  });
  document.getElementById("tab-upload").addEventListener("click", function () {
    switchSource("upload");
  });

  // Chọn file là nạp ngay vào bảng sửa; không gửi API cho tới khi bấm chạy.
  document.getElementById("csv-file").addEventListener("change", loadFileIntoEditor);
  bindEditor();
  bindSaveDialog();

  const trainButtons = [
    document.getElementById("train-button"),
    document.getElementById("preview-run-button"),
    document.getElementById("result-rerun")
  ];
  for (let i = 0; i < trainButtons.length; i++) {
    if (trainButtons[i]) {
      trainButtons[i].addEventListener("click", runProcessingSequence);
    }
  }
  const resultClose = document.getElementById("result-close");
  if (resultClose) {
    resultClose.addEventListener("click", closeResultPanel);
  }
  const loaderCancel = document.getElementById("loader-cancel");
  if (loaderCancel) {
    loaderCancel.addEventListener("click", cancelProcessing);
  }

  bindDemoPreview();
  bindPagination();
  bindTableSearch();
  bindStarDropdown();
  const revealButton = document.getElementById("reveal-data-button");
  if (revealButton) {
    revealButton.addEventListener("click", revealPendingData);
  }
  bindLiveInteractions();

  const metaData = window.WEB_DATA_META;

  if (typeof metaData === "undefined" || !metaData.meta) {
    hideLoader();
    showMissingDataError();
    // Vẫn cho phép chuyển sang tab tải file để dùng API.
    switchSource("upload");
    return;
  }

  applyMetaSettings(metaData);
  // Dựng lại chip nhóm sau khi đã đồng bộ CATEGORY_ORDER với file meta.
  buildPreviewFilterChips();

  // Ghép payload với danh sách review rỗng; preparePreview() nạp review thật
  // ngay để hiện bảng, còn runProcessingSequence() chỉ chạy khi bấm nút.
  state.demoData = {
    meta: metaData.meta,
    summary: metaData.summary,
    technical: metaData.technical,
    reviews: []
  };

  const footerParts = [
    "Sinh từ " + countText(metaData.meta.rows_test) + " review test",
    "ngưỡng " + metaData.meta.threshold.toFixed(2),
    "phiên bản dữ liệu " + (metaData.meta.data_version || "?"),
    "nguồn PostgreSQL (lần chạy model #" + (metaData.meta.model_run_id || "?") + ")",
    "dữ liệu trong DuLieuDemo/data_meta.js + DuLieuDemo/data_reviews.js"
  ];
  document.getElementById("footer-meta").textContent = footerParts.join(" - ");

  // Mở trang ở chế độ xem trước, không tự chạy mô hình và không tự hiện số.
  // Sau khi dữ liệu demo nạp xong, 5 thẻ nhóm + thanh 5 sao đứng yên ở 0;
  // người xem bấm "Hiện lại dữ liệu" thì mới chạy delay + tăng số.
  preparePreview().then(function (loaded) {
    if (loaded) {
      preparePendingReveal();
    } else {
      // Không có dữ liệu thì vẫn cho các thẻ đang hiện xuất hiện gọn gàng.
      playCardEntrance();
    }
  });
});
