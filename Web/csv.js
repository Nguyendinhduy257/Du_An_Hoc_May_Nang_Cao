/*
  Đường dẫn: Du_An_Hoc_May_Nang_Cao\Web\csv.js
  Mục đích : Đọc và ghi CSV ngay trong trình duyệt, để bảng sửa trên web
             xuất ra đúng định dạng mà API Python đọc được.
  Input    : chuỗi CSV (có/không BOM, xuống dòng LF hoặc CRLF).
  Output   : window.CsvTools.parse(text) -> {headers, rows, hasBom, eol}
             window.CsvTools.serialize(headers, rows, options) -> chuỗi CSV.

  Vì sao tách khỏi app.js: hai hàm này không chạm DOM, nên kiểm thử được bằng
  `node` mà không cần trình duyệt. app.js chỉ lo giao diện.
*/

(function (root) {
  "use strict";

  var BOM = "\ufeff";

  // Bỏ BOM ở đầu file. Excel trên Windows hay ghi BOM để nhận ra UTF-8;
  // nếu giữ lại, tên cột đầu tiên sẽ thành "\ufefftext_" và API báo thiếu cột.
  function stripBom(text) {
    return text.charAt(0) === BOM ? text.slice(1) : text;
  }

  // Giữ nguyên kiểu xuống dòng của file gốc khi ghi lại, để diff không bị
  // đổi toàn bộ file chỉ vì trình duyệt thích CRLF.
  function detectEol(text) {
    return text.indexOf("\r\n") !== -1 ? "\r\n" : "\n";
  }

  /*
    Bộ đọc CSV theo RFC 4180 ở mức đủ dùng:
      - trường có dấu phẩy, dấu nháy kép hoặc xuống dòng phải nằm trong "..."
      - hai dấu nháy kép liên tiếp "" trong trường được hiểu là một dấu "
    Không hỗ trợ dấu phân cách khác dấu phẩy, vì csv.DictReader của Python
    cũng chỉ đọc dấu phẩy.
  */
  function parse(text) {
    var hasBom = text.charAt(0) === BOM;
    var eol = detectEol(text);
    var source = stripBom(text);
    var rows = [];
    var row = [];
    var field = "";
    var inQuotes = false;
    var index = 0;

    while (index < source.length) {
      var character = source.charAt(index);

      if (inQuotes) {
        if (character === '"') {
          if (source.charAt(index + 1) === '"') {
            field += '"';
            index += 2;
            continue;
          }
          inQuotes = false;
          index += 1;
          continue;
        }
        field += character;
        index += 1;
        continue;
      }

      if (character === '"') {
        inQuotes = true;
        index += 1;
        continue;
      }
      if (character === ",") {
        row.push(field);
        field = "";
        index += 1;
        continue;
      }
      if (character === "\r" || character === "\n") {
        row.push(field);
        field = "";
        rows.push(row);
        row = [];
        index += character === "\r" && source.charAt(index + 1) === "\n" ? 2 : 1;
        continue;
      }

      field += character;
      index += 1;
    }

    if (field !== "" || row.length > 0) {
      row.push(field);
      rows.push(row);
    }

    // Dòng trống ở cuối file là do dấu xuống dòng cuối, không phải dữ liệu.
    while (rows.length > 0 && rows[rows.length - 1].every(isEmpty)) {
      rows.pop();
    }

    var headers = rows.length > 0 ? rows[0].map(trimCell) : [];
    var body = rows.slice(1).map(function (item) {
      // Dòng thiếu ô (người dùng gõ tay) được đệm rỗng; dòng thừa ô bị cắt,
      // vì API chỉ đọc các cột có trong header.
      var copy = item.slice(0, headers.length);
      while (copy.length < headers.length) {
        copy.push("");
      }
      return copy;
    });

    return { headers: headers, rows: body, hasBom: hasBom, eol: eol };
  }

  function isEmpty(value) {
    return String(value).trim() === "";
  }

  function trimCell(value) {
    return String(value).trim();
  }

  function escapeField(value) {
    var text = value === null || value === undefined ? "" : String(value);
    if (/[",\r\n]/.test(text)) {
      return '"' + text.replace(/"/g, '""') + '"';
    }
    return text;
  }

  function serialize(headers, rows, options) {
    var settings = options || {};
    var eol = settings.eol === "\r\n" ? "\r\n" : "\n";
    var lines = [headers.map(escapeField).join(",")];

    for (var i = 0; i < rows.length; i++) {
      lines.push(rows[i].map(escapeField).join(","));
    }

    var text = lines.join(eol) + eol;
    return (settings.bom ? BOM : "") + text;
  }

  root.CsvTools = { parse: parse, serialize: serialize };
})(typeof window !== "undefined" ? window : globalThis);
