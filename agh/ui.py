"""把审计日志渲染成一个自包含的 HTML 页面。

产物不依赖服务器、不联网、不用装 Python：双击就能看，也能直接发给别人。
日志内容通过 JSON 内嵌 + textContent 渲染，不做 innerHTML 拼接。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .anomaly import RULE_LABELS, Thresholds, detect
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
.card .v { font-size:22px; font-weight:600; margin-top:4px;
           overflow-wrap:anywhere; word-break:break-word; }
.card .v.small { font-size:13px; font-weight:500; line-height:1.5; color:var(--text); }
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
.hash { font-family:ui-monospace,Consolas,monospace; font-size:11.5px; line-height:1.35;
        color:var(--accent); word-break:break-all; user-select:all; }
/* 固定列宽：哈希列吃掉剩余空间，类别/tokens/状态 保持窄且不折行 */
#calls table { table-layout:fixed; }
#calls th:nth-child(1), #calls td:nth-child(1) { width:17%; }
#calls th:nth-child(2), #calls td:nth-child(2) { width:15%; }
#calls th:nth-child(3), #calls td:nth-child(3) { width:7%; white-space:nowrap; }
#calls th:nth-child(4), #calls td:nth-child(4) { width:23%; }
#calls th:nth-child(5), #calls td:nth-child(5) { width:23%; }
#calls th:nth-child(6), #calls td:nth-child(6) { width:7%; white-space:nowrap; }
#calls th:nth-child(7), #calls td:nth-child(7) { width:8%; }
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
      border-radius:8px; overflow:auto; font-size:12px; color:#cfd6e4;
      max-height:420px; white-space:pre-wrap; overflow-wrap:anywhere; }
.help { margin:16px 28px 0; border:1px solid var(--line); border-radius:10px;
        background:var(--panel); padding:0 16px; }
.help > summary { padding:12px 0; font-size:13px; color:var(--text); font-weight:600; }
.help-body { padding:0 0 14px; color:var(--muted); font-size:13px; line-height:1.7; }
.help-body h3 { margin:14px 0 6px; font-size:12.5px; color:var(--text); font-weight:600; }
.help-body ul { margin:6px 0; padding-left:20px; }
.help-body li { margin:3px 0; }
.help-body code { color:var(--accent); }
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
<details class="help">
  <summary>@@L:help_title@@</summary>
  <div class="help-body">@@L:help_body@@</div>
</details>
<section>
  <h2>@@L:calls@@</h2>
  <div class="filters">
    <button id="dl-csv" class="btn">@@L:dl_csv@@</button>
    <select id="f-model"><option value="">@@L:all_models@@</option></select>
    <select id="f-cat"><option value="">@@L:all_categories@@</option></select>
    <label><input type="checkbox" id="f-flagged"> @@L:only_flagged@@</label>
    <input type="text" id="f-search" placeholder="@@L:search@@">
    <span class="count" id="f-count"></span>
  </div>
  <div id="calls"></div>
</section>
<section>
  <h2>@@L:anomaly_section@@</h2>
  <div id="anomalies"></div>
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
  ["@@L:card_calls@@", DATA.summary.calls, ""],
  ["Tokens", DATA.summary.tokens, ""],
  ["@@L:card_flags@@", DATA.summary.flags, ""],
  ["@@L:card_anomalies@@", DATA.summary.anomalies || 0, ""],
  ["@@L:card_models@@", (DATA.summary.models || []).join(" / ") || "—", "small"],
];
for (const [k, v, cls] of cards) {
  const c = text("div", "", "card");
  c.appendChild(text("div", k, "k"));
  c.appendChild(text("div", v, cls ? `v ${cls}` : "v"));
  $("cards").appendChild(c);
}

// 类别下拉：从数据里收集
const catSelect = $("f-cat");
const cats = [...new Set(DATA.calls.map((c) => c.category).filter(Boolean))].sort();
for (const cat of cats) {
  const opt = document.createElement("option");
  opt.value = cat;
  opt.textContent = cat;
  catSelect.appendChild(opt);
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
const anomalous = new Map();
for (const a of (DATA.anomalies || [])) {
  for (const cid of (a.call_ids || [a.call_id])) {
    if (!anomalous.has(cid)) anomalous.set(cid, []);
    if (!anomalous.get(cid).includes(a.label)) anomalous.get(cid).push(a.label);
  }
}

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
  const hits = anomalous.get(c.call_id);
  if (hits && hits.length) {
    const pill = text("span", `@@L:status_anomaly@@ ${hits.join(" / ")}`, "pill p-warn");
    pill.style.marginTop = "4px";
    pill.title = hits.join("\n");
    wrap.appendChild(pill);
  }
  if (c.prompt) {
    const d = document.createElement("details");
    d.appendChild(text("summary", "@@L:show_raw@@"));
    d.appendChild(text("pre", `@@L:io@@`));
    wrap.appendChild(d);
  }
  return [c.call_id, c.model, c.category || "—",
          text("code", c.prompt_sha256 || "—", "hash"),
          text("code", c.response_sha256 || "—", "hash"),
          c.tokens, wrap];
}

function renderCalls() {
  const model = modelSelect.value;
  const category = $("f-cat").value;
  const onlyFlagged = $("f-flagged").checked;
  const q = $("f-search").value.trim().toLowerCase();
  const rows = DATA.calls.filter((c) => {
    if (model && c.model !== model) return false;
    if (category && (c.category || "") !== category) return false;
    if (onlyFlagged && !flagged.has(c.call_id)) return false;
    if (q) {
      const hay = `${c.call_id} ${c.model} ${c.category || ""} ${c.prompt_sha256} ${c.response_sha256}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const host = $("calls");
  host.replaceChildren();
  host.appendChild(table(
    ["@@L:th_call_id@@", "@@L:th_model@@", "@@L:th_category@@",
     "@@L:th_input@@", "@@L:th_output@@", "tokens", "@@L:th_status@@"],
    rows.map(rowFor)
  ));
  $("f-count").textContent = `@@L:count@@`;
}

modelSelect.addEventListener("change", renderCalls);
catSelect.addEventListener("change", renderCalls);
$("f-flagged").addEventListener("change", renderCalls);
$("f-search").addEventListener("input", renderCalls);
renderCalls();

$("anomalies").appendChild(table(
  ["@@L:th_rule@@", "@@L:th_call_id@@", "@@L:th_detail@@"],
  (DATA.anomalies || []).map((a) => [a.label, a.call_id, a.detail])
));

$("flags").appendChild(table(
  ["@@L:th_call_id@@", "@@L:th_reason@@", "@@L:th_note@@"],
  DATA.flags.map((f) => [f.call_id, f.reason, f.note])
));

$("dl-csv").addEventListener("click", () => {
  const head = ["call_id","model","category","tokens","prompt_sha256","response_sha256",
                "flagged","flag_reason","flag_note","anomalies"];
  const flaggedMap = new Map(DATA.flags.map((f) => [f.call_id, f]));
  const esc = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
  const lines = [head.join(",")];
  for (const c of DATA.calls) {
    const f = flaggedMap.get(c.call_id) || {};
    lines.push([
      c.call_id, c.model, c.category || "", c.tokens, c.prompt_sha256, c.response_sha256,
      f.call_id ? "yes" : "no", f.reason || "", f.note || "",
      (anomalous.get(c.call_id) || []).join("|"),
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


def _count_categories(calls: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in calls:
        key = str(call.get("category") or "")
        if key:
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def build_report(
    log_path: str | Path,
    *,
    title: str = "AGH 审计报告",
    max_calls: int | None = None,
    anomalies: bool = True,
    thresholds: Thresholds | None = None,
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
                    "category": payload.get("category", ""),
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

    findings = detect(calls, thresholds=thresholds) if anomalies else []

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
        "anomalies": [
            {
                "rule": f.rule,
                "label": RULE_LABELS.get(f.rule, f.rule),
                "call_id": f.call_id,
                # 组级命中只标代表调用，否则一轮对话几十步会全部染红
                "call_ids": list(f.all_ids()) if not f.group else [f.call_id],
                "detail": f.detail,
            }
            for f in findings
        ],
        "summary": {
            "calls": len(calls),
            "tokens": sum(int(c["tokens"] or 0) for c in calls),
            "flags": len(flags),
            "anomalies": len(findings),
            "models": sorted({c["model"] for c in calls if c["model"]}),
            "categories": _count_categories(calls),
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
        "anomaly_section": "自动检查（纯统计，不判断对错）",
        "card_anomalies": "自动发现",
        "status_anomaly": "自动",
        "th_rule": "规则",
        "th_detail": "说明",
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
        "th_call_id": "调用 ID",
        "th_category": "类别",
        "all_categories": "全部类别",
        "th_input": "输入哈希",
        "th_output": "输出哈希",
        "th_status": "状态",
        "count": "显示 ${rows.length} / ${DATA.calls.length} 条",
        "th_reason": "原因",
        "th_note": "备注",
        "th_event": "事件",
        "th_summary": "摘要",
        "help_title": "使用说明（点开看）",
        "help_body": """
<h3>这个页面是什么</h3>
一份自包含的审计报告。数据全部嵌在 HTML 里，不联网、不请求后端，可以直接发给别人。
页首徽章表示哈希链校验结果：绿色「哈希链校验通过」= 日志从写入那一刻起没有被改过；
红色则表示某一条内容对不上，徽章下面会给出断链位置。

<h3>页首那几个数字</h3>
<ul>
<li><b>调用次数</b>：日志里 llm.call 事件的条数。</li>
<li><b>Tokens</b>：这些调用记录的 token 用量之和。注意这是日志里记的数，
不是账单；如果导入时只记了「新算 token」，缓存读的部分不含在内。</li>
<li><b>标记问题</b>：调用 <code>session.flag()</code> 记录的人工标记数。为 0 只说明
「没人标过」，不代表「没有问题」。</li>
<li><b>自动发现</b>：纯统计规则挑出来的可疑调用（token 突增、重复输入、空响应、
tokens 为 0）。它不判断对错，只是提示「这条值得看一眼」。人工标记和自动发现分开计，
不要混着看。</li>
<li><b>模型</b>：日志里出现过的模型名，按字母序。同一个模型的不同写法会被算成两个。</li>
</ul>

<h3>表格各列</h3>
<ul>
<li><b>调用 ID</b>：由输入输出的哈希前缀 + 序号生成，用来关联标记。它不含模型名，
所以同样的输入换模型跑，ID 会重复。</li>
<li><b>类别</b>：调用方自己标的分类（<code>agh import</code> 或
<code>session.call(category=...)</code>）。没标的显示「—」。</li>
<li><b>输入哈希 / 输出哈希</b>：输入输出原文的 SHA-256 前 16 位。报告默认只给哈希，
不直接展示原文，避免把敏感内容随手发出去。要看原文点行内的「看原文」。</li>
<li><b>tokens</b>：这次调用记录的 token 数。</li>
<li><b>状态</b>：正常 / 已标记。</li>
</ul>

<h3>怎么自己验一遍</h3>
在命令行跑 <code>agh audit verify --log &lt;日志文件&gt;</code>，
输出 <code>{"ok": true}</code> 表示哈希链完整。
报告里的「校验通过」是生成页面时算的，不能替代你自己验。

<h3>这个报告不能告诉你什么</h3>
<ul>
<li>哪次调用贵得离谱、哪次响应慢 —— 它只做审计，不做成本/性能分析</li>
<li>日志是不是被整条替换过 —— 本地哈希链发现不了，需要外部锚定
（<code>agh anchor</code>）</li>
<li>记录本身在写入前是否真实 —— 签名只能证明「从某一刻起没被改」</li>
<li>所有问题 —— 自动检查只有四条统计规则，它没报不等于没问题</li>
</ul>

<h3>隐私</h3>
默认只展示哈希。HTML 里仍然内嵌了原文（为了「看原文」可用），
发给别人前请确认：<code>agh ui</code> 生成的页面等于完整日志内容。
""",
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
        "anomaly_section": "Automatic checks (statistics only, not a verdict)",
        "card_anomalies": "Auto-flagged",
        "status_anomaly": "auto",
        "th_rule": "rule",
        "th_detail": "detail",
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
        "th_call_id": "call_id",
        "th_category": "category",
        "all_categories": "All categories",
        "th_input": "input hash",
        "th_output": "output hash",
        "th_status": "status",
        "count": "Showing ${rows.length} / ${DATA.calls.length}",
        "th_reason": "reason",
        "th_note": "note",
        "th_event": "event",
        "th_summary": "summary",
        "help_title": "How to read this report (click to expand)",
        "help_body": """
<h3>What this page is</h3>
A self-contained audit report. All data is embedded in the HTML — no network, no backend —
so you can hand it to someone else as a single file.
The badge at the top shows the hash-chain check: green "Hash chain verified" means the log
has not been altered since it was written. Red means some entry does not match the chain,
and the failing position is shown right under the badge.

<h3>The numbers at the top</h3>
<ul>
<li><b>Calls</b>: number of <code>llm.call</code> events in the log.</li>
<li><b>Tokens</b>: sum of the token counts recorded in those calls. This is what the log says,
not a bill. If the import only recorded freshly computed tokens, cached reads are not included.</li>
<li><b>Flagged</b>: number of manual <code>session.flag()</code> marks. Zero only means
"nobody flagged anything", not "nothing is wrong".</li>
<li><b>Auto-flagged</b>: calls picked out by purely statistical rules (token spike,
repeated input, empty response, zero tokens). It is not a verdict — just "worth a look".
Manual flags and automatic findings are counted separately on purpose.</li>
<li><b>Models</b>: model names found in the log, alphabetically. Different spellings of the
same model are counted as separate entries.</li>
</ul>

<h3>Columns</h3>
<ul>
<li><b>call_id</b>: hash prefix of input/output plus a sequence number; used to attach flags.
It does not include the model name, so the same input run through a different model reuses the ID.</li>
<li><b>category</b>: a label supplied by the caller (via <code>agh import</code> or
<code>session.call(category=...)</code>). Shows "—" when absent.</li>
<li><b>input hash / output hash</b>: first 16 hex chars of the SHA-256 of the input/output text.
The report only shows hashes by default so sensitive content is not casually shared.
Click "Show raw" inside a row to see the text.</li>
<li><b>tokens</b>: token count recorded for that call.</li>
<li><b>status</b>: ok / flagged.</li>
</ul>

<h3>Verifying it yourself</h3>
Run <code>agh audit verify --log &lt;file&gt;</code> on the command line.
<code>{"ok": true}</code> means the hash chain is intact. The badge in this page was computed
when the page was generated; it does not replace your own check.

<h3>What this report cannot tell you</h3>
<ul>
<li>Which call was expensive or slow — this is an audit, not cost/performance analytics</li>
<li>Whether the whole log was replaced — a local hash chain cannot detect that;
you need external anchoring (<code>agh anchor</code>)</li>
<li>Whether the record was true before it was written — a signature only proves
"unchanged since a certain moment"</li>
<li>Every problem — the automatic checks are four statistical rules only;
silence is not proof of health</li>
</ul>

<h3>Privacy</h3>
Only hashes are displayed, but the full text is still embedded in the HTML so "Show raw" works.
Before sharing, remember: this page contains the complete log content.
""",
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
    log_path: str | Path,
    *,
    max_calls: int | None = None,
    lang: str = "zh",
    anomalies: bool = True,
) -> str:
    data = build_report(log_path, max_calls=max_calls, anomalies=anomalies)
    labels = _LABELS.get(lang) or _LABELS["zh"]
    data["title"] = labels["title"]
    data["footer"] = labels["footer"]
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    # 先替换文案占位符，再塞数据：数据里的内容不会被当成占位符
    return _apply_labels(_TEMPLATE, lang).replace("__DATA__", payload)


__all__ = ["LANGS", "build_report", "render_html"]
