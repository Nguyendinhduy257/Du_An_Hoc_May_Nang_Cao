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
  technical: null,       // số liệu biểu đồ đã vẽ, để vẽ lại khi đổi sáng/tối
  hasTrueLabel: false,   // chỉ dữ liệu demo mới có nhãn thật
  filter: "genuine",     // mặc định chỉ giữ review hữu ích
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

function redrawCharts() {
  // Biểu đồ SVG đã vẽ xong thì đổi token CSS không tự đổi màu hình, nên phải
  // vẽ lại từ số liệu đã lưu.
  if (state.technical) {
    renderTechnical(state.technical.data, state.technical.meta);
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

  redrawCharts();
}

function initTheme() {
  const stored = readStoredTheme();
  // Mặc định nền sáng: trang dùng để trình bày báo cáo trên máy chiếu.
  applyTheme(stored === "dark" ? "dark" : "light");

  const button = document.getElementById("theme-toggle");
  if (!button) {
    return;
  }

  button.addEventListener("click", function () {
    const next = currentTheme() === "dark" ? "light" : "dark";
    storeTheme(next);
    applyTheme(next);
  });
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

const loaderState = {
  screen: null,
  title: null,
  detail: null,
  log: null,
  track: null,
  fill: null,
  timer: null,
  startedAt: 0,
  timerId: 0,
  limitSeconds: 0
};

function loaderPart(key, id) {
  if (!loaderState[key]) {
    loaderState[key] = document.getElementById(id);
  }
  return loaderState[key];
}

function pause(milliseconds) {
  return new Promise(function (resolve) {
    window.setTimeout(resolve, milliseconds);
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

// null = chưa biết tiến độ, cho thanh chạy qua lại thay vì bịa phần trăm.
function setLoaderProgress(percent) {
  const track = loaderPart("track", "loader-track");
  const fill = loaderPart("fill", "loader-fill");
  if (!track || !fill) {
    return;
  }

  if (percent === null) {
    track.classList.add("is-indeterminate");
    track.removeAttribute("aria-valuenow");
    return;
  }

  track.classList.remove("is-indeterminate");
  const clamped = Math.max(0, Math.min(100, percent));
  fill.style.width = clamped + "%";
  track.setAttribute("aria-valuenow", String(Math.round(clamped)));
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
  document.body.classList.add("is-processing");
  resetLoaderLog();
  setLoaderText(title, detail);
  setLoaderProgress(typeof settings.progress === "number" ? settings.progress : null);

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
  window.clearInterval(loaderState.timerId);
  loaderState.timerId = 0;
  screen.classList.add("is-hidden");
  document.body.classList.remove("is-processing");
  const timer = loaderPart("timer", "loader-timer");
  if (timer) {
    timer.textContent = "";
  }
}

// Đếm lại nhóm/số sao ngay trong trình duyệt. Đây là việc thật, dùng để vừa
// hiện tiến độ vừa đối chiếu với con số Python đã xuất trong data_meta.js.
function aggregateDemoReviews(reviews, onProgress) {
  return new Promise(function (resolve) {
    const totals = { total: 0, useful: 0, categories: {}, stars: {} };
    let index = 0;

    function step() {
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

      onProgress(reviews.length > 0 ? index / reviews.length : 1);

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

// Chạy tuần tự: khởi động -> nạp review -> đếm -> áp ngưỡng -> dựng báo cáo.
// Toàn bộ nằm dưới lớp phủ, nên người xem thấy "đang xử lý" chứ không thấy
// kết quả demo bật ra sẵn.
async function runProcessingSequence() {
  const demo = state.demoData;
  const summary = demo.summary;
  const threshold = demo.meta.threshold;
  const replayButton = document.getElementById("replay-button");

  state.source = "demo";
  document.getElementById("tab-demo").classList.add("is-active");
  document.getElementById("tab-upload").classList.remove("is-active");
  document.getElementById("upload-card").hidden = true;
  setPayloadVisibility(false);
  document.getElementById("technical-section").hidden = true;
  replayButton.hidden = true;
  updateSourceNote();
  renderBadges();

  showLoader(
    "Khởi động mô hình",
    "Nạp vectorizer TF-IDF và hệ số Logistic Regression...",
    { progress: 5 }
  );
  await pause(BOOT_PAUSE_MS);
  completeLoaderStep(
    "Khởi động mô hình",
    "Logistic Regression + TF-IDF · ngưỡng " + threshold.toFixed(2)
  );

  setLoaderText(
    "Nạp dữ liệu demo",
    "Đọc " + countText(summary.total) + " review từ DuLieuDemo/data_reviews.js..."
  );
  setLoaderProgress(15);
  const reviews = await ensureDemoReviews();
  await pause(BOOT_PAUSE_MS);

  if (!Array.isArray(reviews) || reviews.length === 0) {
    hideLoader();
    document.getElementById("technical-section").hidden = false;
    renderTechnical(demo.technical, demo.meta);
    applyPayload(demo, "demo");
    setPayloadVisibility(true);
    setTableMessage(
      "Không nạp được data_reviews.js. Hãy chạy: python MaNguon\\export_web_data.py",
      true
    );
    replayButton.hidden = false;
    return;
  }

  completeLoaderStep(
    "Nạp dữ liệu demo",
    countText(reviews.length) + " review từ data_reviews.js"
  );

  setLoaderText(
    "Trích đặc trưng",
    "Chuẩn hoá chữ và đếm token trên từng review..."
  );
  const aggregate = await aggregateDemoReviews(reviews, function (ratio) {
    setLoaderProgress(15 + ratio * 45);
  });
  await pause(BOOT_PAUSE_MS);
  completeLoaderStep(
    "Trích đặc trưng",
    countText(aggregate.total) + " review · " +
    countText(aggregate.useful) + " hữu ích"
  );

  setLoaderText(
    "Dự đoán xác suất",
    "Áp ngưỡng " + threshold.toFixed(2) + " và xếp nhóm cho từng review..."
  );
  setLoaderProgress(70);
  await pause(BOOT_PAUSE_MS);
  completeLoaderStep(
    "Dự đoán xác suất",
    "Ngưỡng " + threshold.toFixed(2) + " · " +
    loaderCategorySummary(aggregate.categories)
  );

  setLoaderText(
    "Tổng hợp báo cáo",
    "Dựng bảng 5 sao, bộ lọc và biểu đồ..."
  );
  setLoaderProgress(86);
  demo.reviews = reviews;

  // Phải hiện thẻ kỹ thuật TRƯỚC khi vẽ: SVG đo chiều rộng thật, thẻ đang
  // display:none sẽ cho chiều rộng 0 và biểu đồ bị bóp lại.
  document.getElementById("technical-section").hidden = false;
  renderTechnical(demo.technical, demo.meta);
  applyPayload(demo, "demo");
  setPayloadVisibility(true);
  updateSourceNote();
  renderBadges();
  await pause(BOOT_PAUSE_MS);
  completeLoaderStep(
    "Tổng hợp báo cáo",
    "5 nhóm · bảng 5 sao · biểu đồ cho " +
    countText(aggregate.total) + " review"
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
  setLoaderProgress(100);
  await pause(BOOT_PAUSE_MS);
  hideLoader();
  replayButton.hidden = false;
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

function makeCategoryTag(categoryId) {
  const info = categoryInfo(categoryId);

  const tag = document.createElement("span");
  tag.className = "category-tag " + categoryClass(categoryId);

  tag.appendChild(document.createTextNode(info.label));
  return tag;
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

    card.appendChild(createDiv("category-count", countText(count)));
    card.appendChild(createDiv("category-percent", percent.toFixed(1) + "%"));

    const bar = createDiv("category-bar");
    const fill = createDiv("category-bar-fill");
    fill.style.width = percent + "%";
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

function makeStarMeter(value, maxValue, fillClass) {
  const cell = createDiv("star-meter");

  const track = createDiv("star-meter-track");
  const fill = createDiv("star-meter-fill " + fillClass);
  const width = maxValue > 0 ? (value / maxValue) * 100 : 0;
  fill.style.width = Math.min(100, width) + "%";
  track.appendChild(fill);

  cell.appendChild(track);
  cell.appendChild(createDiv("star-meter-count", countText(value)));
  return cell;
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

    const ratingCell = createDiv("star-rating");
    ratingCell.appendChild(createDiv("star-glyphs", starsText(value)));
    ratingCell.appendChild(createDiv("star-value", value + " sao"));
    row.appendChild(ratingCell);

    row.appendChild(makeStarMeter(allCount, maxAll, "fill-all"));
    row.appendChild(makeStarMeter(usefulCount, maxAll, "fill-useful"));

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

function setFilter(filterId) {
  state.filter = filterId;
  state.currentPage = 1;

  renderSummary();
  renderFilterChips();
  renderTable();

  const tableCard = document.getElementById("table-card");
  tableCard.scrollIntoView({ behavior: "smooth", block: "start" });
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
}

/* ============================================================
   Bảng review
   ============================================================ */

function getVisibleRows() {
  if (state.filter === "all") {
    return state.rows;
  }

  const visible = [];
  for (let i = 0; i < state.rows.length; i++) {
    if (state.rows[i].category === state.filter) {
      visible.push(state.rows[i]);
    }
  }
  return visible;
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
  textCell.appendChild(createDiv("review-text", review.text));

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
  starCell.appendChild(createDiv("star-glyphs", starsText(review.rating)));
  if (review.rating !== null && review.rating !== undefined) {
    starCell.appendChild(createDiv("star-number", Number(review.rating).toFixed(1)));
  }
  tableRow.appendChild(starCell);

  const categoryCell = document.createElement("td");
  categoryCell.className = "category-cell";
  categoryCell.appendChild(makeCategoryTag(review.category));

  // Nhãn cơ sở ngay dưới tên nhóm, để từng dòng cũng nói rõ model hay luật.
  const rowBasis = review.category_basis
    ? review.category_basis
    : basisForCategory(review.category);
  categoryCell.appendChild(makeBasisTag(rowBasis));
  tableRow.appendChild(categoryCell);

  tableRow.appendChild(makeProbabilityCell(review.prob_fake, info.tone));

  if (state.hasTrueLabel) {
    const truthCell = document.createElement("td");
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
  if (review.flags && review.flags.length > 0) {
    for (let i = 0; i < review.flags.length; i++) {
      const flagName = review.flags[i];
      const flagLabel = FLAG_INFO[flagName] || flagName;
      flagCell.appendChild(makeTag(flagLabel, "tag-flag flag-" + flagName));
    }
  } else {
    flagCell.textContent = "—";
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
  state.currentPage = 1;

  renderSummary();
  renderStarPanel();
  renderFilterChips();
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

  const showTechnical = source === "demo" && state.demoData !== null;
  document.getElementById("technical-section").hidden = !showTechnical;

  updateSourceNote();
  renderBadges();
}

/* ============================================================
   Số liệu kỹ thuật (giữ nguyên cách vẽ của bản báo cáo cũ)
   ============================================================ */

function renderKpis(testMetrics) {
  const container = document.getElementById("kpi-grid");
  container.innerHTML = "";

  const items = [
    ["Accuracy", testMetrics.accuracy, "Tỉ lệ đoán đúng toàn bộ", false],
    ["Precision", testMetrics.precision, "Trong số báo Giả, bao nhiêu đúng", false],
    ["Recall", testMetrics.recall, "Trong số Giả thật, bắt được bao nhiêu", false],
    ["F1", testMetrics.f1, "Cân bằng Precision và Recall", true],
    ["ROC-AUC", testMetrics.roc_auc, "Khả năng tách hai lớp", false],
    ["PR-AUC", testMetrics.pr_auc, "Diện tích dưới đường Precision-Recall", false]
  ];

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const card = createDiv(item[3] ? "kpi is-highlight" : "kpi");
    card.appendChild(createDiv("kpi-label", item[0]));
    card.appendChild(createDiv("kpi-value", percentText(item[1])));
    card.appendChild(createDiv("kpi-note", item[2]));
    container.appendChild(card);
  }
}

function makeConfusionCell(kind, value, label) {
  const cell = createDiv("confusion-cell cell-" + kind);
  cell.appendChild(createDiv("value", countText(value)));
  cell.appendChild(createDiv("label", label));
  return cell;
}

function renderConfusion(matrix) {
  const container = document.getElementById("confusion-grid");
  container.innerHTML = "";

  // Hàng 1: ô trống góc trên trái + 2 tiêu đề cột (nhãn dự đoán).
  container.appendChild(createDiv("confusion-axis", ""));
  container.appendChild(createDiv("confusion-axis", "Dự đoán: Thật (0)"));
  container.appendChild(createDiv("confusion-axis", "Dự đoán: Giả (1)"));

  // Hàng 2: nhãn thật = Thật.
  container.appendChild(createDiv("confusion-axis", "Thực tế: Thật (0)"));
  container.appendChild(makeConfusionCell("tn", matrix.tn, "TN - đúng là thật"));
  container.appendChild(makeConfusionCell("fp", matrix.fp, "FP - báo nhầm là giả"));

  // Hàng 3: nhãn thật = Giả.
  container.appendChild(createDiv("confusion-axis", "Thực tế: Giả (1)"));
  container.appendChild(makeConfusionCell("fn", matrix.fn, "FN - bỏ sót review giả"));
  container.appendChild(makeConfusionCell("tp", matrix.tp, "TP - đúng là giả"));

  const legend = document.getElementById("confusion-legend");
  legend.innerHTML = "";
  const notes = [
    "TN (True Negative): review thật, model cũng nói thật.",
    "FP (False Positive): review thật nhưng bị gắn oan là giả.",
    "FN (False Negative): review giả nhưng lọt qua.",
    "TP (True Positive): review giả, model bắt đúng."
  ];
  for (let i = 0; i < notes.length; i++) {
    const item = document.createElement("li");
    item.textContent = notes[i];
    legend.appendChild(item);
  }
}

function niceStep(maxValue) {
  // Chọn bước chia trục Y "đẹp": 1, 2, 5, 10, 20, 50, 100...
  if (maxValue <= 0) {
    return 1;
  }
  const rawStep = maxValue / 5;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const candidates = [1, 2, 5, 10];
  for (let i = 0; i < candidates.length; i++) {
    if (rawStep <= candidates[i] * magnitude) {
      return candidates[i] * magnitude;
    }
  }
  return 10 * magnitude;
}

function binLabel(histogram, index) {
  const low = histogram.bin_edges[index].toFixed(2);
  const high = histogram.bin_edges[index + 1].toFixed(2);
  return low + " - " + high;
}

function makeBar(x, y, width, height, fill, tooltip) {
  const group = createSvg("g", {});
  if (height > 0.5) {
    group.appendChild(
      createSvg("rect", {
        x: x,
        y: y,
        width: width,
        height: height,
        rx: 2,
        fill: fill
      })
    );
  }
  const title = createSvg("title", {});
  title.textContent = tooltip;
  group.appendChild(title);
  return group;
}

function renderHistogram(histogram, threshold) {
  const container = document.getElementById("histogram-chart");
  container.innerHTML = "";

  const realCounts = histogram.real_counts;
  const fakeCounts = histogram.fake_counts;
  const binCount = realCounts.length;

  const width = 760;
  const height = 340;
  const left = 56;
  const right = 16;
  const top = 16;
  const bottom = 48;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  let maxValue = 0;
  for (let i = 0; i < binCount; i++) {
    maxValue = Math.max(maxValue, realCounts[i], fakeCounts[i]);
  }
  const step = niceStep(maxValue);
  const yMax = Math.max(step, Math.ceil(maxValue / step) * step);

  const svg = createSvg("svg", {
    viewBox: "0 0 " + width + " " + height,
    role: "img"
  });

  // Lưới ngang + nhãn trục Y.
  const tickCount = 5;
  for (let i = 0; i <= tickCount; i++) {
    const value = (yMax / tickCount) * i;
    const y = top + plotHeight - (value / yMax) * plotHeight;
    svg.appendChild(
      createSvg("line", {
        x1: left,
        y1: y,
        x2: left + plotWidth,
        y2: y,
        stroke: themeColor("--chart-grid", "#d9e2ee"),
        "stroke-width": 1
      })
    );
    svg.appendChild(textNode(left - 10, y + 4, countText(Math.round(value)), "end"));
  }

  const binWidth = plotWidth / binCount;
  const barWidth = Math.max(4, (binWidth - 8) / 2);

  for (let i = 0; i < binCount; i++) {
    const xBase = left + i * binWidth + 4;
    const realHeight = (realCounts[i] / yMax) * plotHeight;
    const fakeHeight = (fakeCounts[i] / yMax) * plotHeight;

    svg.appendChild(
      makeBar(
        xBase,
        top + plotHeight - realHeight,
        barWidth,
        realHeight,
        themeColor("--chart-real", "#8fa0b6"),
        "Thật | khoảng " + binLabel(histogram, i) + " | " + realCounts[i] + " review"
      )
    );
    svg.appendChild(
      makeBar(
        xBase + barWidth + 2,
        top + plotHeight - fakeHeight,
        barWidth,
        fakeHeight,
        themeColor("--chart-fake", "#2563eb"),
        "Giả | khoảng " + binLabel(histogram, i) + " | " + fakeCounts[i] + " review"
      )
    );
  }

  // Nhãn trục X.
  for (let i = 0; i <= 5; i++) {
    const value = i / 5;
    const x = left + value * plotWidth;
    svg.appendChild(textNode(x, top + plotHeight + 22, value.toFixed(1), "middle"));
  }
  svg.appendChild(
    textNode(left + plotWidth / 2, height - 6, "Xác suất model gán nhãn Giả", "middle")
  );

  // Đường ngưỡng quyết định.
  const thresholdX = left + threshold * plotWidth;
  svg.appendChild(
    createSvg("line", {
      x1: thresholdX,
      y1: top,
      x2: thresholdX,
      y2: top + plotHeight,
      stroke: themeColor("--chart-marker", "#16202f"),
      "stroke-width": 2,
      "stroke-dasharray": "6 5"
    })
  );
  svg.appendChild(
    textNode(thresholdX + 6, top + 14, "ngưỡng " + threshold.toFixed(2), "start", themeColor("--chart-marker", "#16202f"))
  );

  container.appendChild(svg);
}

function renderThresholdCurve(points, bestThreshold) {
  const container = document.getElementById("curve-chart");
  container.innerHTML = "";

  const width = 760;
  const height = 340;
  const left = 56;
  const right = 16;
  const top = 16;
  const bottom = 48;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const firstThreshold = points[0].threshold;
  const lastThreshold = points[points.length - 1].threshold;

  function xOf(threshold) {
    return left + ((threshold - firstThreshold) / (lastThreshold - firstThreshold)) * plotWidth;
  }

  function yOf(value) {
    return top + plotHeight - value * plotHeight;
  }

  const svg = createSvg("svg", {
    viewBox: "0 0 " + width + " " + height,
    role: "img"
  });

  // Lưới ngang + nhãn trục Y (0.0 -> 1.0).
  for (let i = 0; i <= 5; i++) {
    const value = i / 5;
    const y = yOf(value);
    svg.appendChild(
      createSvg("line", {
        x1: left,
        y1: y,
        x2: left + plotWidth,
        y2: y,
        stroke: themeColor("--chart-grid", "#d9e2ee"),
        "stroke-width": 1
      })
    );
    svg.appendChild(textNode(left - 10, y + 4, value.toFixed(1), "end"));
  }

  // Ba đường: mỗi đường là một chuỗi điểm nối bằng lệnh M/L của SVG path.
  // Chỉ dùng sắc độ của màu nhấn + xám, không dùng ba màu khác nhau để tránh
  // biến biểu đồ thành "cầu vồng". F1 là chỉ số chính nên đậm nhất.
  const series = [
    ["precision", themeColor("--chart-s1", "#8fa0b6")],
    ["recall", themeColor("--chart-s2", "#5b9bff")],
    ["f1", themeColor("--chart-s3", "#2563eb")]
  ];

  for (let s = 0; s < series.length; s++) {
    const fieldName = series[s][0];
    const color = series[s][1];

    let pathData = "";
    for (let i = 0; i < points.length; i++) {
      const x = xOf(points[i].threshold);
      const y = yOf(points[i][fieldName]);
      pathData = pathData + (i === 0 ? "M" : "L") + x.toFixed(2) + " " + y.toFixed(2) + " ";
    }

    svg.appendChild(
      createSvg("path", {
        d: pathData,
        fill: "none",
        stroke: color,
        "stroke-width": 2.4,
        "stroke-linejoin": "round"
      })
    );
  }

  // Nhãn trục X.
  for (let i = 1; i <= 9; i += 2) {
    const value = i / 10;
    svg.appendChild(textNode(xOf(value), top + plotHeight + 22, value.toFixed(1), "middle"));
  }
  svg.appendChild(
    textNode(left + plotWidth / 2, height - 6, "Ngưỡng quyết định", "middle")
  );

  // Đánh dấu ngưỡng đã chọn.
  const markerX = xOf(bestThreshold);
  svg.appendChild(
    createSvg("line", {
      x1: markerX,
      y1: top,
      x2: markerX,
      y2: top + plotHeight,
      stroke: themeColor("--chart-marker", "#16202f"),
      "stroke-width": 2,
      "stroke-dasharray": "6 5"
    })
  );
  svg.appendChild(
    textNode(markerX + 6, top + 14, "chọn " + bestThreshold.toFixed(2), "start", themeColor("--chart-marker", "#16202f"))
  );

  container.appendChild(svg);
}

function renderLegend(containerId, items) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  for (let i = 0; i < items.length; i++) {
    const wrapper = document.createElement("span");
    wrapper.className = "legend-item";

    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = items[i][1];

    wrapper.appendChild(swatch);
    wrapper.appendChild(document.createTextNode(items[i][0]));
    container.appendChild(wrapper);
  }
}

function renderReliability(calibration) {
  const container = document.getElementById("reliability-chart");
  if (!container) {
    return;
  }
  container.innerHTML = "";

  if (!calibration || !Array.isArray(calibration.reliability_bins)) {
    container.textContent = "Không có dữ liệu hiệu chuẩn.";
    return;
  }

  const bins = calibration.reliability_bins;

  const width = 760;
  const height = 340;
  const left = 56;
  const right = 16;
  const top = 16;
  const bottom = 48;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  // Cả hai trục đều là xác suất 0..1 nên dùng chung một tỷ lệ.
  function toX(value) {
    return left + value * plotWidth;
  }
  function toY(value) {
    return top + plotHeight - value * plotHeight;
  }

  const svg = createSvg("svg", {
    viewBox: "0 0 " + width + " " + height,
    role: "img"
  });

  // Lưới + nhãn trục.
  for (let i = 0; i <= 5; i++) {
    const value = i / 5;
    svg.appendChild(
      createSvg("line", {
        x1: left,
        y1: toY(value),
        x2: left + plotWidth,
        y2: toY(value),
        stroke: themeColor("--chart-grid", "#d9e2ee"),
        "stroke-width": 1
      })
    );
    svg.appendChild(textNode(left - 10, toY(value) + 4, value.toFixed(1), "end"));
    svg.appendChild(
      textNode(toX(value), top + plotHeight + 22, value.toFixed(1), "middle")
    );
  }

  // Đường chéo: nếu xác suất hoàn hảo thì điểm nằm đúng trên đường này.
  svg.appendChild(
    createSvg("line", {
      x1: toX(0),
      y1: toY(0),
      x2: toX(1),
      y2: toY(1),
      stroke: themeColor("--chart-real", "#8fa0b6"),
      "stroke-width": 2,
      "stroke-dasharray": "6 5"
    })
  );

  // Mỗi điểm là một khoảng xác suất. Bán kính theo số review trong khoảng
  // để khoảng đông review được nhìn thấy rõ hơn.
  let maxCount = 1;
  for (let i = 0; i < bins.length; i++) {
    maxCount = Math.max(maxCount, bins[i].count);
  }

  for (let i = 0; i < bins.length; i++) {
    const bin = bins[i];
    if (bin.count === 0 || bin.mean_predicted === null) {
      continue;
    }

    const radius = 4 + (bin.count / maxCount) * 8;
    const circle = createSvg("circle", {
      cx: toX(bin.mean_predicted),
      cy: toY(bin.observed_fake_rate),
      r: radius,
      fill: themeColor("--chart-band", "rgba(37, 99, 235, 0.35)"),
      stroke: themeColor("--chart-s3", "#2563eb"),
      "stroke-width": 1.5
    });

    const title = createSvg("title", {});
    title.textContent =
      "Khoảng " + bin.low.toFixed(1) + "–" + bin.high.toFixed(1) +
      " | dự đoán " + bin.mean_predicted.toFixed(3) +
      " | thực tế " + bin.observed_fake_rate.toFixed(3) +
      " | " + bin.count + " review";
    circle.appendChild(title);
    svg.appendChild(circle);
  }

  svg.appendChild(
    textNode(left + plotWidth / 2, height - 6, "Xác suất model dự đoán", "middle")
  );
  container.appendChild(svg);

  const summary = document.getElementById("reliability-summary");
  if (summary) {
    summary.textContent =
      "Brier score: " + calibration.brier_before + " → " + calibration.brier_after +
      " (càng nhỏ càng tốt) · Sai số hiệu chuẩn ECE: " +
      calibration.ece_before + " → " + calibration.ece_after +
      ". Điểm càng gần đường chéo thì xác suất càng đáng tin.";
  }
}

function renderTechnical(technical, meta) {
  if (!technical) {
    return;
  }

  state.technical = { data: technical, meta: meta };

  const testMetrics = technical.metrics.test;
  renderKpis(testMetrics);
  renderConfusion(testMetrics.confusion_matrix);

  renderLegend("histogram-legend", [
    ["Nhãn thật: Thật", themeColor("--chart-real", "#8fa0b6")],
    ["Nhãn thật: Giả", themeColor("--chart-fake", "#2563eb")],
    ["Ngưỡng quyết định", themeColor("--chart-marker", "#16202f")]
  ]);
  renderHistogram(technical.histogram, meta.threshold);

  renderLegend("curve-legend", [
    ["Precision", themeColor("--chart-s1", "#8fa0b6")],
    ["Recall", themeColor("--chart-s2", "#5b9bff")],
    ["F1", themeColor("--chart-s3", "#2563eb")],
    ["Ngưỡng được chọn", themeColor("--chart-marker", "#16202f")]
  ]);
  renderThresholdCurve(technical.threshold_curve, meta.threshold);

  // Hiệu chuẩn xác suất: bằng chứng cho thấy con số hiển thị đáng tin.
  renderLegend("reliability-legend", [
    ["Hiệu chuẩn hoàn hảo", themeColor("--chart-real", "#8fa0b6")],
    ["Thực tế quan sát", themeColor("--chart-s3", "#2563eb")]
  ]);
  renderReliability(technical.metrics.calibration);
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
  showLoader(phases[0][0], phases[0][1], {
    progress: null,
    limitSeconds: translateRows ? translateSeconds : 0
  });

  const phaseTimer = window.setInterval(function () {
    phaseIndex = Math.min(phaseIndex + 1, phases.length - 1);
    setLoaderText(phases[phaseIndex][0], phases[phaseIndex][1]);
  }, UPLOAD_PHASE_MS);

  const runButton = document.getElementById("editor-run");
  const replayButton = document.getElementById("replay-button");
  runButton.disabled = true;
  // Ẩn nút chạy lại trong lúc chờ API: bấm vào sẽ khởi động chuỗi demo song
  // song và tắt màn hình chờ khi request này còn đang bay.
  replayButton.hidden = true;
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

    if (!response.ok) {
      setEditorStatus(data.error || "API trả về lỗi.", true);
      return;
    }

    state.uploadData = data;
    state.uploadFileName = fileName;
    switchSource("upload");

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
    setLoaderProgress(100);
    await pause(UPLOAD_RESULT_HOLD_MS);

    document.getElementById("summary-card").scrollIntoView({
      behavior: "smooth",
      block: "start"
    });
  } catch (error) {
    setEditorStatus(
      "Không gọi được API. Hãy chạy: python MaNguon/api_server.py rồi mở " +
      "http://127.0.0.1:8000/ (không double-click file).",
      true
    );
  } finally {
    window.clearInterval(phaseTimer);
    hideLoader();
    runButton.disabled = false;
    replayButton.hidden = false;
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
  document.getElementById("replay-button").addEventListener("click", function () {
    runProcessingSequence();
  });

  bindPagination();

  const metaData = window.WEB_DATA_META;

  if (typeof metaData === "undefined" || !metaData.meta) {
    hideLoader();
    showMissingDataError();
    // Vẫn cho phép chuyển sang tab tải file để dùng API.
    switchSource("upload");
    return;
  }

  applyMetaSettings(metaData);

  // Ghép payload với danh sách review rỗng; review thật được nạp trong
  // runProcessingSequence() để màn hình chờ có việc thật mà báo tiến độ.
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

  // Không vẽ kết quả ngay: chạy tuần tự dưới màn hình chờ rồi mới hiện.
  runProcessingSequence();
});
