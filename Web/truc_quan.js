/*
  Đường dẫn: Du_An_Hoc_May_Nang_Cao\Web\truc_quan.js
  Mục đích : Toàn bộ biểu đồ và số liệu của riêng trang trực quan hóa.
  Input    : window.WEB_DATA_META (data_meta.js), token màu từ style.css.
  Output   : nội dung các id trong truc_quan.html.
  Ghi chú  : mã vẽ được dời nguyên từ app.js để trang review chính không còn
             phụ thuộc vào biểu đồ. Đổi nền sáng/tối thì vẽ lại từ số liệu cũ.
*/

"use strict";

const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
const THEME_STORAGE_KEY = "fake-review-theme";
const SIDEBAR_STORAGE_KEY = "fake-review-sidebar";

let technicalData = null;
let metaData = null;

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

  const button = document.getElementById("viz-theme-toggle");
  if (button) {
    button.setAttribute("aria-pressed", isDark ? "true" : "false");
    button.title = isDark ? "Chuyển sang nền sáng" : "Chuyển sang nền tối";
  }

  const icon = document.getElementById("viz-theme-icon");
  if (icon) {
    icon.textContent = isDark ? "\u2600" : "\u263e";
  }

  // Nhãn "Thiết lập" cố định trong sidebar; biểu tượng và title đã nói trạng
  // thái nền, không cần đổi chữ làm lệch thứ tự menu.
  redrawCharts();
}

function initTheme() {
  applyTheme(currentTheme());

  const button = document.getElementById("viz-theme-toggle");
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
   Menu dọc bên trái (dùng chung key lưu với trang review chính)
   ============================================================ */

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

function initSidebar() {
  const button = document.getElementById("menu-toggle");
  if (!button) {
    return;
  }

  syncSidebarToggle();
  button.addEventListener("click", function () {
    const collapsed = !isSidebarCollapsed();
    document.documentElement.setAttribute("data-sidebar", collapsed ? "collapsed" : "open");
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "collapsed" : "open");
    } catch {
      // localStorage bị chặn: vẫn đổi giao diện trong phiên hiện tại.
    }
    syncSidebarToggle();
  });
}

/* ============================================================
   Tiện ích tạo phần tử
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

/* ============================================================
   Các biểu đồ (giữ nguyên cách vẽ của bản báo cáo cũ)
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

  container.appendChild(createDiv("confusion-axis", ""));
  container.appendChild(createDiv("confusion-axis", "Dự đoán: Thật (0)"));
  container.appendChild(createDiv("confusion-axis", "Dự đoán: Giả (1)"));

  container.appendChild(createDiv("confusion-axis", "Thực tế: Thật (0)"));
  container.appendChild(makeConfusionCell("tn", matrix.tn, "TN - đúng là thật"));
  container.appendChild(makeConfusionCell("fp", matrix.fp, "FP - báo nhầm là giả"));

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

  for (let i = 0; i <= 5; i++) {
    const value = i / 5;
    const x = left + value * plotWidth;
    svg.appendChild(textNode(x, top + plotHeight + 22, value.toFixed(1), "middle"));
  }
  svg.appendChild(
    textNode(left + plotWidth / 2, height - 6, "Xác suất model gán nhãn Giả", "middle")
  );

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

  for (let i = 1; i <= 9; i += 2) {
    const value = i / 10;
    svg.appendChild(textNode(xOf(value), top + plotHeight + 22, value.toFixed(1), "middle"));
  }
  svg.appendChild(
    textNode(left + plotWidth / 2, height - 6, "Ngưỡng quyết định", "middle")
  );

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
      "Khoảng " + bin.low.toFixed(1) + "\u2013" + bin.high.toFixed(1) +
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

function redrawCharts() {
  if (!technicalData || !metaData) {
    return;
  }
  renderTechnical(technicalData, metaData);
}

function renderTechnical(technical, meta) {
  technicalData = technical;
  metaData = meta;

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

  renderLegend("reliability-legend", [
    ["Hiệu chuẩn hoàn hảo", themeColor("--chart-real", "#8fa0b6")],
    ["Thực tế quan sát", themeColor("--chart-s3", "#2563eb")]
  ]);
  renderReliability(technical.metrics.calibration);
}

document.addEventListener("DOMContentLoaded", function () {
  initTheme();
  initSidebar();

  const meta = window.WEB_DATA_META;
  if (!meta || !meta.technical || !meta.meta) {
    return;
  }

  renderTechnical(meta.technical, meta.meta);

  const footer = document.getElementById("viz-footer");
  if (footer) {
    footer.textContent =
      "Dữ liệu từ DuLieuDemo/data_meta.js · sinh ngày " + meta.meta.generated_at +
      " · phiên bản " + meta.meta.data_version + " · " +
      countText(meta.meta.rows_test) + " review test.";
  }
});
