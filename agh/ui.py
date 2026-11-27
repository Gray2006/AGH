"""把审计日志渲染成一个自包含的 HTML 页面。

产物不依赖服务器、不联网、不用装 Python：双击就能看，也能直接发给别人。
日志内容通过 JSON 内嵌 + textContent 渲染，不做 innerHTML 拼接。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .eventlog import EventLog, LogEntry, LogTampered

_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@L:title@@</title>
<style>
:root { --bg:#0f1115; --panel:#171a21; --line:#262b36; --text:#e6e8ee; --muted:#8b93a7;
        --ok:#3fb950; --warn:#d29922; --bad:#f85149; --accent:#58a6ff; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font:14px/1.55 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
header { padding:24px 28px 18px; border-bottom:1px solid var(--line); }
h1 { margin:0 0 6px; font-size:20px; font-weight:600; }
.sub { color:var(--muted); font-size:12.5px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
         gap:12px; padding:18px 28px; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
.card .k { color:var(--muted); font-size:12px; }
.card .v { font-size:22px; font-weight:600; margin-top:4px; }
section { padding:6px 28px 22px; }
h2 { font-size:14px; color:var(--muted); font-weight:600; margin:18px 0 10px;
     text-transform:uppercase; letter-spacing:.06em; }
table { width:100%; border-collapse:collapse; background:var(--panel);
        border:1px solid var(--line); border-radius:10px; overflow:hidden; }
th,td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--line);
        vertical-align:top; font-size:13px; }
th { color:var(--muted); font-weight:500; background:#1b1f28; }
tr:last-child td { border-bottom:none; }
code { font-family:ui-monospace,Consolas,monospace; font-size:12px; color:var(--accent);
       word-break:break-all; }
.pill { display:inline-block; padding:1px 8px; border-radius:999px; font-size:11.5px; }
#verify { margin-top:8px; }
.btn { background:var(--panel); color:var(--text); border:1px solid var(--line);
       border-radius:8px; padding:5px 12px; font-size:12.5px; cursor:pointer; }
.btn:hover { border-color:var(--accent); color:var(--accent); }
.p-ok { background:rgba(63,185,80,.15); color:var(--ok); }
.p-bad { background:rgba(248,81,73,.15); color:var(--bad); }
.p-warn { background:rgba(210,153,34,.15); color:var(--warn); }
details { margin-top:6px; }
summary { cursor:pointer; color:var(--accent); font-size:12px; }
pre { margin:6px 0 0; padding:10px; background:#0b0d11; border:1px solid var(--line);
      border-radius:8px; overflow:auto; font-size:12px; color:#cfd6e4; }
.empty { color:var(--muted); padding:14px 0; }
.filters { display:flex; gap:10px; align-items:center; margin:0 28px 14px; flex-wrap:wrap; }
.filters select, .filters input[type=text] { background:var(--panel); color:var(--text);
  border:1px solid var(--line); border-radius:8px; padding:6px 10px; font-size:13px; }
.filters input[type=text] { min-width:220px; }
.filters label { color:var(--muted); font-size:13px; display:flex; align-items:center; gap:6px; }
.count { color:var(--muted); font-size:12px; margin-left:auto; }
footer { padding:14px 28px 28px; color:var(--muted); font-size:12px; border-top:1px solid var(--line); }
</style>
</head>
<body>
<header>
  <h1 id="title">@@L:title@@</h1>
  <div class="sub" id="meta"></div>
  <div id="verify"></div>
</header>
<div class="cards" id="cards"></div>
<section>
  <h2>@@L:calls@@</h2>
  <div class="filters">
    <button id="dl-csv" class="btn">@@L:dl_csv@@</button>
    <select id="f-model"><option value="">@@L:all_models@@</option></select>
    <label><input type="checkbox" id="f-flagged"> @@L:only_flagged@@</label>
    <input type="text" id="f-search" placeholder="@@L:search@@">
    <span class="count" id="f-count"></span>
  </div>
  <div id="calls"></div>
</section>
<section>
  <h2>@@L:flagged_section@@</h2>
  <div id="flags"></div>
</section>
<section>
  <h2>@@L:timeline@@</h2>
  <div id="timeline"></div>
</section>
<footer id="footer"></footer>
<script>
const DATA = __DATA__;
const $ = (id) => document.getElementById(id);
const text = (tag, value, cls) => {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  el.textContent = value == null ? "" : String(value);
  return el;
};
const short = (s, n) => { s = String(s || ""); return s.length > n ? s.slice(0, n) + "…" : s; };

$("title").textContent = DATA.title || "@@L:title@@";
const badge = document.createElement("span");
badge.className = DATA.verified ? "pill p-ok" : "pill p-bad";
badge.textContent = DATA.verified ? "@@L:verified_ok@@" : "@@L:verified_bad@@";
$("verify").appendChild(badge);
if (!DATA.verified && DATA.verify_error) {
  $("verify").appendChild(text("div", DATA.verify_error, "sub"));
}
$("meta").textContent = `@@L:meta@@`;
$("footer").textContent = DATA.footer;
if (DATA.truncated) {
  const msg = `@@L:truncated@@`;
  const banner = text("div", msg, "empty");
  document.querySelector("header").appendChild(banner);
}

const cards = [
  ["@@L:card_calls@@", DATA.summary.calls],
  ["Tokens", DATA.summary.tokens],
  ["@@L:card_flags@@", DATA.summary.flags],
  ["@@L:card_models@@", (DATA.summary.models || []).join(" / ") || "—"],
];
for (const [k, v] of cards) {
  const c = text("div", "", "card");
  c.appendChild(text("div", k, "k"));
  c.appendChild(text("div", v, "v"));
  $("cards").appendChild(c);
}

function table(headers, rows) {
  if (!rows.length) return text("div", "@@L:empty@@", "empty");
  const t = document.createElement("table");
  const thead = document.createElement("thead");
  const tr = document.createElement("tr");
  headers.forEach((h) => tr.appendChild(text("th", h)));
  thead.appendChild(tr);
  t.appendChild(thead);
  const tbody = document.createElement("tbody");
  rows.forEach((cells) => {
    const row = document.createElement("tr");
    cells.forEach((cell) => {
      const td = document.createElement("td");
      if (cell instanceof Node) td.appendChild(cell); else td.textContent = cell;
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });
  t.appendChild(tbody);
  return t;
}

const flagged = new Set(DATA.flags.map((f) => f.call_id));

// 模型下拉：从数据里收集，按字母序
const modelSelect = $("f-model");
const models = [...new Set(DATA.calls.map((c) => c.model).filter(Boolean))].sort();
for (const m of models) {
  const opt = document.createElement("option");
  opt.value = m;
  opt.textContent = m;
  modelSelect.appendChild(opt);
}

function rowFor(c) {
  const isFlagged = flagged.has(c.call_id);
  const status = text("span", isFlagged ? "@@L:status_flagged@@" : "@@L:status_ok@@",
                      isFlagged ? "pill p-bad" : "pill p-ok");
  const wrap = document.createElement("div");
  wrap.appendChild(status);
  if (c.prompt) {
    const d = document.createElement("details");
    d.appendChild(text("summary", "@@L:show_raw@@"));
    d.appendChild(text("pre", `@@L:io@@`));
    wrap.appendChild(d);
  }
  return [c.call_id, c.model, short(c.prompt_sha256, 16), short(c.response_sha256, 16), c.tokens, wrap];
}

function renderCalls() {
  const model = modelSelect.value;
  const onlyFlagged = $("f-flagged").checked;
  const q = $("f-search").value.trim().toLowerCase();
  const rows = DATA.calls.filter((c) => {
    if (model && c.model !== model) return false;
    if (onlyFlagged && !flagged.has(c.call_id)) return false;
    if (q) {
      const hay = `${c.call_id} ${c.model} ${c.prompt_sha256} ${c.response_sha256}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const host = $("calls");
  host.replaceChildren();
  host.appendChild(table(
    ["call_id", "@@L:th_model@@", "@@L:th_input@@", "@@L:th_output@@", "tokens", "@@L:th_status@@"],
    rows.map(rowFor)
  ));
  $("f-count").textContent = `@@L:count@@`;
}

modelSelect.addEventListener("change", renderCalls);
$("f-flagged").addEventListener("change", renderCalls);
$("f-search").addEventListener("input", renderCalls);
renderCalls();

$("flags").appendChild(table(
  ["call_id", "@@L:th_reason@@", "@@L:th_note@@"],
  DATA.flags.map((f) => [f.call_id, f.reason, f.note])
));

$("dl-csv").addEventListener("click", () => {
  const head = ["call_id","model","tokens","prompt_sha256","response_sha256","flagged","flag_reason","flag_note"];
  const flaggedMap = new Map(DATA.flags.map((f) => [f.call_id, f]));
  const esc = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
  const lines = [head.join(",")];
  for (const c of DATA.calls) {
    const f = flaggedMap.get(c.call_id) || {};
    lines.push([
      c.call_id, c.model, c.tokens, c.prompt_sha256, c.response_sha256,
      f.call_id ? "yes" : "no", f.reason || "", f.note || "",
    ].map(esc).join(","));
  }
  const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "agh-calls.csv";
  a.click();
  URL.revokeObjectURL(a.href);
});

$("timeline").appendChild(table(
  ["#", "@@L:th_event@@", "@@L:th_summary@@"],
  DATA.events.map((e) => [e.seq, e.type, e.brief])
));
</script>
</body>
</html>
"""


def _brief(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "llm.call":
        return f"{payload.get('model', '')} · {payload.get('tokens', 0)} tokens"
    if event_type == "llm.flag":
        return f"{payload.get('reason', '')} · {payload.get('note', '')}"
    if event_type == "session.start":
        return f"label={payload.get('label', '')}"
    if event_type == "session.end":
        return "ok" if payload.get("ok") else f"异常：{payload.get('error', '')}"
    keys = list(payload)[:3]
    return ", ".join(f"{k}={payload[k]}" for k in keys)


def _salvage(path: Path) -> list[Any]:
    """日志整体读不回来时，逐条捡能解析的行，保住报告里可看的部分。"""
    entries: list[Any] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            entries.append(
                LogEntry(
                    seq=raw["seq"],
                    ts=raw["ts"],
                    type=raw["type"],
                    payload=raw["payload"],
                    prev_hash=raw["prev_hash"],
                    hash=raw["hash"],
                )
            )
        except (ValueError, KeyError, TypeError):
            continue
    return entries


def build_report(
    log_path: str | Path, *, title: str = "AGH 审计报告", max_calls: int | None = None
) -> dict[str, Any]:
    path = Path(log_path)
    # 校验失败不能让报告生成失败：报告的最大用途恰恰是「把一份可疑日志发给别人看」。
    # JSON 坏到读不回来的，逐条尽力收回能读的部分，页面顶上标红说明原因。
    log = EventLog()
    log.path = path
    verified = True
    verify_error = ""
    try:
        log.entries = log.read()
        log.verify()
    except LogTampered as exc:
        verified = False
        verify_error = str(exc)
        log.entries = _salvage(path)

    calls: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for entry in log.entries:
        payload = dict(entry.payload)
        events.append({"seq": entry.seq, "type": entry.type, "brief": _brief(entry.type, payload)})
        if entry.type == "llm.call":
            calls.append(
                {
                    "call_id": payload.get("call_id", ""),
                    "model": payload.get("model", ""),
                    "tokens": payload.get("tokens", 0),
                    "prompt_sha256": payload.get("prompt_sha256", ""),
                    "response_sha256": payload.get("response_sha256", ""),
                    "prompt": payload.get("prompt", ""),
                    "response": payload.get("response", ""),
                }
            )
        elif entry.type == "llm.flag":
            flags.append(
                {
                    "call_id": payload.get("call_id", ""),
                    "reason": payload.get("reason", ""),
                    "note": payload.get("note", ""),
                }
            )

    total_calls = len(calls)
    truncated = False
    if max_calls is not None and total_calls > max_calls:
        # 大日志（几万条）会把 HTML 撑到几十 MB，浏览器直接卡死。
        # 截断时保留标记过的调用，其余按原顺序取前 N 条。
        flagged_ids = {f["call_id"] for f in flags}
        kept = [c for c in calls if c["call_id"] in flagged_ids][:max_calls]
        kept_ids = {c["call_id"] for c in kept}
        for call in calls:
            if len(kept) >= max_calls:
                break
            if call["call_id"] not in kept_ids:
                kept.append(call)
        calls = kept
        truncated = True

    return {
        "title": title,
        "verified": verified,
        "verify_error": verify_error,
        "truncated": truncated,
        "total_calls": total_calls,
        "log": str(path),
        "head": log.head(),
        "entries": len(log.entries),
        "calls": calls,
        "flags": flags,
        "events": events,
        "summary": {
            "calls": len(calls),
            "tokens": sum(int(c["tokens"] or 0) for c in calls),
            "flags": len(flags),
            "models": sorted({c["model"] for c in calls if c["model"]}),
        },
        "footer": "本页面由 agh ui 生成，数据内嵌、不联网。哈希链校验请在命令行运行 agh audit verify。",
    }


_LABELS: dict[str, dict[str, str]] = {
    "zh": {
        "title": "AGH 审计报告",
        "calls": "模型调用",
        "dl_csv": "下载 CSV",
        "all_models": "全部模型",
        "only_flagged": "只看已标记",
        "search": "搜索 call_id / 模型 / 哈希",
        "flagged_section": "被标记的问题",
        "timeline": "事件时间线",
        "verified_ok": "哈希链校验通过",
        "verified_bad": "哈希链校验未通过",
        "meta": "日志：${DATA.log}　链头：${DATA.head.slice(0, 16)}　事件：${DATA.entries}",
        "truncated": (
            "日志共 ${DATA.total_calls} 次调用，报告只渲染前 ${DATA.calls.length} 条"
            "（已标记的优先保留）。用 --max-calls 调整。"
        ),
        "card_calls": "调用次数",
        "card_flags": "标记问题",
        "card_models": "模型",
        "empty": "没有记录。",
        "status_flagged": "已标记",
        "status_ok": "正常",
        "show_raw": "看原文",
        "io": '输入：\\n${c.prompt}\\n\\n输出：\\n${c.response || ""}',
        "th_model": "模型",
        "th_input": "输入哈希",
        "th_output": "输出哈希",
        "th_status": "状态",
        "count": "显示 ${rows.length} / ${DATA.calls.length} 条",
        "th_reason": "原因",
        "th_note": "备注",
        "th_event": "事件",
        "th_summary": "摘要",
        "footer": "本页面由 agh ui 生成，数据内嵌、不联网。哈希链校验请在命令行运行 agh audit verify。",
    },
    "en": {
        "title": "AGH Audit Report",
        "calls": "Model calls",
        "dl_csv": "Download CSV",
        "all_models": "All models",
        "only_flagged": "Flagged only",
        "search": "Search call_id / model / hash",
        "flagged_section": "Flagged issues",
        "timeline": "Event timeline",
        "verified_ok": "Hash chain verified",
        "verified_bad": "Hash chain verification FAILED",
        "meta": "Log: ${DATA.log}　Head: ${DATA.head.slice(0, 16)}　Events: ${DATA.entries}",
        "truncated": (
            "Log has ${DATA.total_calls} calls; report renders the first "
            "${DATA.calls.length} (flagged kept first). Adjust with --max-calls."
        ),
        "card_calls": "Calls",
        "card_flags": "Flagged",
        "card_models": "Models",
        "empty": "No records.",
        "status_flagged": "flagged",
        "status_ok": "ok",
        "show_raw": "Show raw",
        "io": 'Input:\\n${c.prompt}\\n\\nOutput:\\n${c.response || ""}',
        "th_model": "model",
        "th_input": "input hash",
        "th_output": "output hash",
        "th_status": "status",
        "count": "Showing ${rows.length} / ${DATA.calls.length}",
        "th_reason": "reason",
        "th_note": "note",
        "th_event": "event",
        "th_summary": "summary",
        "footer": (
            "Generated by agh ui. Data is embedded; no network calls. "
            "Verify the hash chain with `agh audit verify` on the command line."
        ),
    },
}

LANGS = tuple(_LABELS)


def _apply_labels(html: str, lang: str) -> str:
    labels = _LABELS.get(lang) or _LABELS["zh"]
    for key, value in labels.items():
        html = html.replace(f"@@L:{key}@@", value)
    return html


def render_html(
    log_path: str | Path, *, max_calls: int | None = None, lang: str = "zh"
) -> str:
    data = build_report(log_path, max_calls=max_calls)
    labels = _LABELS.get(lang) or _LABELS["zh"]
    data["title"] = labels["title"]
    data["footer"] = labels["footer"]
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    # 先替换文案占位符，再塞数据：数据里的内容不会被当成占位符
    return _apply_labels(_TEMPLATE, lang).replace("__DATA__", payload)


__all__ = ["LANGS", "build_report", "render_html"]
