"""把审计日志渲染成一个自包含的 HTML 页面。

产物不依赖服务器、不联网、不用装 Python：双击就能看，也能直接发给别人。
日志内容通过 JSON 内嵌 + textContent 渲染，不做 innerHTML 拼接。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .eventlog import EventLog

_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AGH 审计报告</title>
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
  <h1 id="title">AGH 审计报告</h1>
  <div class="sub" id="meta"></div>
</header>
<div class="cards" id="cards"></div>
<section>
  <h2>模型调用</h2>
  <div class="filters">
    <select id="f-model"><option value="">全部模型</option></select>
    <label><input type="checkbox" id="f-flagged"> 只看已标记</label>
    <input type="text" id="f-search" placeholder="搜索 call_id / 模型 / 哈希">
    <span class="count" id="f-count"></span>
  </div>
  <div id="calls"></div>
</section>
<section>
  <h2>被标记的问题</h2>
  <div id="flags"></div>
</section>
<section>
  <h2>事件时间线</h2>
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

$("title").textContent = DATA.title || "AGH 审计报告";
$("meta").textContent = `日志：${DATA.log}　链头：${DATA.head.slice(0, 16)}　事件：${DATA.entries}`;
$("footer").textContent = DATA.footer;

const cards = [
  ["调用次数", DATA.summary.calls],
  ["Tokens", DATA.summary.tokens],
  ["标记问题", DATA.summary.flags],
  ["模型", (DATA.summary.models || []).join(" / ") || "—"],
];
for (const [k, v] of cards) {
  const c = text("div", "", "card");
  c.appendChild(text("div", k, "k"));
  c.appendChild(text("div", v, "v"));
  $("cards").appendChild(c);
}

function table(headers, rows) {
  if (!rows.length) return text("div", "没有记录。", "empty");
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
  const status = text("span", isFlagged ? "已标记" : "正常",
                      isFlagged ? "pill p-bad" : "pill p-ok");
  const wrap = document.createElement("div");
  wrap.appendChild(status);
  if (c.prompt) {
    const d = document.createElement("details");
    d.appendChild(text("summary", "看原文"));
    d.appendChild(text("pre", `输入：\n${c.prompt}\n\n输出：\n${c.response || ""}`));
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
    ["call_id", "模型", "输入", "输出", "tokens", "状态"],
    rows.map(rowFor)
  ));
  $("f-count").textContent = `显示 ${rows.length} / ${DATA.calls.length} 条`;
}

modelSelect.addEventListener("change", renderCalls);
$("f-flagged").addEventListener("change", renderCalls);
$("f-search").addEventListener("input", renderCalls);
renderCalls();

$("flags").appendChild(table(
  ["call_id", "原因", "备注"],
  DATA.flags.map((f) => [f.call_id, f.reason, f.note])
));

$("timeline").appendChild(table(
  ["#", "事件", "摘要"],
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


def build_report(log_path: str | Path, *, title: str = "AGH 审计报告") -> dict[str, Any]:
    path = Path(log_path)
    log = EventLog(path)
    log.verify()

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

    return {
        "title": title,
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


def render_html(log_path: str | Path) -> str:
    data = build_report(log_path)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _TEMPLATE.replace("__DATA__", payload)


__all__ = ["build_report", "render_html"]
