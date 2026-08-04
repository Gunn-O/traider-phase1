# ============================================================================
# bt/viewer.py
# ----------------------------------------------------------------------------
# HTML viewer แบบ MT5 — offline 100% (วาดบน <canvas> ด้วย vanilla JS, ไม่มี dependency)
# อ่าน OHLC (list[Bar]) + trades → เขียน viewer.html ไฟล์เดียว (ฝังข้อมูล+JS)
# วาด: แท่งเทียน + pan/zoom + marker entry/exit + เส้น SL/TP + รายการจุดเข้า (ค้นหา/คลิกกระโดด)
#
# v1: แสดงเฉพาะไม้ที่ fill+ปิดแล้ว (ไม้ที่ไม่ fill = milestone ถัดไป ต้องให้ engine เก็บเพิ่ม)
# ============================================================================
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict

# renderer JS = shared source เดียว (bt/viewer_render.js) — baked viewer (เดิม) inline จากตรงนี้
# · dynamic viewer (Phase 1c) จะ reuse ไฟล์เดียวกัน → ไม่ drift
_RENDER_JS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer_render.js")


def _ohlc_payload(bars) -> dict:
    t, o, h, l, c = [], [], [], [], []
    for b in bars:
        t.append(int(b.time.timestamp()))
        o.append(round(b.open, 3)); h.append(round(b.high, 3))
        l.append(round(b.low, 3));  c.append(round(b.close, 3))
    return {"t": t, "o": o, "h": h, "l": l, "c": c}


def _trades_payload(trades) -> list[dict]:
    return [{
        "plan": t["plan_id"], "tag": t["tag"], "dir": t["direction"], "kind": t["kind"],
        "eb": t["entry_bar"], "xb": t["exit_bar"],
        "entry": round(t["entry"], 3), "sl": round(t["sl"], 3),
        "tp": round(t["tp"], 3), "exit": round(t["exit_price"], 3),
        "result": t["result"], "lot": t["lot"],
        "pnl": t["pnl_pips"], "pnlusd": t["pnl_usd"],
    } for t in trades]


def _unfilled_payload(unfilled) -> list[dict]:
    out = []
    for u in (unfilled or []):
        lp, sl, tp = u.get("limit_price"), u.get("sl"), u.get("tp")
        out.append({
            "plan": u.get("plan_id"), "tag": u.get("tag"), "dir": u.get("direction"),
            "pb": u.get("place_bar"), "db": u.get("death_bar"),
            "price": round(lp, 3) if lp is not None else None,
            "sl": round(sl, 3) if sl is not None else None,
            "tp": round(tp, 3) if tp is not None else None,
            "reason": u.get("reason"),
        })
    return out


def _safe_int(v):
    """int หรือ None (field ขาด/ว่าง) — กัน viewer พังกับ plan_meta run เก่า"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _read_plan_meta(out_path: str) -> list[dict]:
    """อ่าน plan_meta.csv (พ่อ/แม่/%/เหตุผล) จากโฟลเดอร์เดียวกับ viewer.html
    — Phase A เขียนไฟล์นี้ก่อนเรียก viewer แล้ว · ไม่มีไฟล์ → [] (เช่น unit test)"""
    p = os.path.join(os.path.dirname(out_path), "plan_meta.csv")
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            reasons = (row.get("reasons") or "").split(" · ")
            # schema-tolerant: father/mother (mai_ruay) อ่านแบบ .get → None ถ้าไม่มี (เช่น mountain)
            #   ป้องกัน KeyError ตอน strategy ใช้ plan_meta คนละชุด (ฐาน/ยอด) — JS guard pm.fs==null อยู่แล้ว
            rec = {
                "plan": _safe_int(row.get("plan_id")),
                "fs":   _safe_int(row.get("father_start_bar")),
                "fe":   _safe_int(row.get("father_end_bar")),
                "fp":   row.get("father_pct"),       # string — รักษาทศนิยม 1 ตำแหน่ง
                "mb":   _safe_int(row.get("mother_bar")),
                "mp":   row.get("mother_pct"),
                "reasons": [r for r in reasons if r],
            }
            # passthrough คอลัมน์อื่น (เช่น base_bar/peak_bar/height ของ mountain) → payload สำหรับ renderer ภายหลัง
            for k, v in row.items():
                if k not in ("plan_id", "father_start_bar", "father_end_bar",
                             "father_pct", "mother_bar", "mother_pct", "reasons"):
                    rec[k] = v
            out.append(rec)
    return out


def _plans_payload(trades) -> list[dict]:
    groups = defaultdict(list)
    for t in trades:
        groups[t["plan_id"]].append(t)
    out = []
    for pid in sorted(groups):
        g = groups[pid]
        net = round(sum(t["pnl_usd"] for t in g), 2)
        out.append({
            "plan_id": pid, "direction": g[0]["direction"],
            "entry_time": min(str(t["entry_time"]) for t in g),
            "eb": min(t["entry_bar"] for t in g),
            "n_trades": len(g), "net_pnl_usd": net,
            "result": "WIN" if net > 0 else "LOSS",
        })
    return out


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_subhead(out_path: str) -> str:
    """strategy + config จาก config_used.yaml (_run) ในโฟลเดอร์เดียวกับ viewer.html
    — run เก่าไม่มีไฟล์/field → แสดงเท่าที่มี (ว่างได้ ไม่ error)"""
    p = os.path.join(os.path.dirname(out_path), "config_used.yaml")
    if not os.path.exists(p):
        return ""
    try:
        import yaml
        with open(p, encoding="utf-8") as f:
            c = yaml.safe_load(f) or {}
        rm = c.get("_run") if isinstance(c, dict) else None
        rm = rm if isinstance(rm, dict) else {}
    except Exception:  # noqa: BLE001 — header เสริม ห้ามทำ viewer ล่ม
        return ""
    parts = []
    if rm.get("strategy"):
        parts.append('<span class="sh-strat">' + _esc(rm["strategy"]) + '</span>')
    if rm.get("config"):
        parts.append('<span class="sh-cfg">' + _esc(os.path.basename(str(rm["config"]))) + '</span>')
    return ' · '.join(parts)


def build_viewer_html(data: dict, title: str = "backtest", subhead: str = "") -> str:
    """ประกอบ HTML self-contained = _TEMPLATE + inline shared renderer (viewer_render.js) + bake DATA
    ใช้ร่วม auto-bake (write_viewer) + on-demand export (server) → single source ไม่ drift
    · auto-bake: data ไม่มี 'equity' → output เท่าเดิม · export: ใส่ DATA.equity → มีแผง equity"""
    with open(_RENDER_JS_PATH, encoding="utf-8") as f:
        render_js = f.read()
    # inline shared JS ก่อน (มี __DATA__ อยู่ข้างใน) → แล้วค่อยฝัง DATA · ลำดับ replace สำคัญ
    return (_TEMPLATE
            .replace("__TITLE__", title)
            .replace("__SUBHEAD__", subhead)
            .replace("__RENDER_JS__", render_js)
            .replace("__DATA__", json.dumps(data, separators=(",", ":"))))


def write_viewer(bars, trades, out_path: str, title: str = "backtest",
                 unfilled=None) -> str:
    data = {
        "ohlc": _ohlc_payload(bars),
        "trades": _trades_payload(trades),
        "plans": _plans_payload(trades),
        "unfilled": _unfilled_payload(unfilled),
        "plan_meta": _read_plan_meta(out_path),
    }   # auto-bake = ไม่มี equity (พฤติกรรม/byte เท่าเดิม)
    html = build_viewer_html(data, title=title, subhead=_build_subhead(out_path))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;background:#0e0e12;color:#cfd2dc;font:13px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;display:flex;height:100vh;overflow:hidden}
 #side{width:290px;flex:none;background:#15161c;border-right:1px solid #23252e;display:flex;flex-direction:column}
 #side h1{font-size:14px;margin:10px 12px 2px;color:#e8eaf0}
 #subhead{font-size:11px;margin:0 12px 6px;color:#8a90a0;font-family:ui-monospace,Menlo,monospace;line-height:1.5;word-break:break-all}
 #subhead .sh-strat{color:#e8c07a}
 #subhead .sh-cfg{color:#9ec1ff}
 #ulegend{font-size:10.5px;color:#8a90a0;margin:0 12px 6px;line-height:1.7;font-family:ui-monospace,Menlo,monospace}
 #ulegend span{margin-right:10px;white-space:nowrap}
 #stat{padding:0 12px 8px;font-size:12px;color:#9aa0b0}
 #search{margin:6px 12px;padding:6px 8px;background:#0e0e12;border:1px solid #2a2d38;color:#cfd2dc;border-radius:4px}
 #list{flex:1;overflow:auto}
 .row{padding:6px 12px;border-bottom:1px solid #1c1e26;cursor:pointer}
 .row:hover{background:#1c1e28}
 .win{border-left:3px solid #26a69a}.loss{border-left:3px solid #ef5350}
 .row.unf{border-left:3px solid #6a6f80;opacity:.62}
 .row .nf{color:#7a8093;font-size:11px;font-style:italic}
 .row .t{color:#9aa0b0;font-size:11px}
 #main{flex:1;position:relative}
 canvas{display:block;cursor:crosshair}
 #cvx{position:absolute;top:0;left:0;pointer-events:none}   /* crosshair overlay — เลเยอร์บน #cv (ไม่รับเมาส์) */
 #tip{position:absolute;top:26px;left:10px;pointer-events:none;font:12px/1.4 ui-monospace,Menlo,monospace;white-space:nowrap;text-shadow:0 1px 2px #000,0 0 3px #000;display:none;z-index:5}
 #bar{position:absolute;top:6px;left:10px;font-size:12px;color:#9aa0b0;pointer-events:none}
 #help{position:absolute;bottom:6px;left:10px;font-size:11px;color:#5a5f70;pointer-events:none}
 /* ── glass strip toolbar (overlay ลอยมุมขวาบน · เว้นแกนราคา 62px) ── */
 #xtoggle{position:absolute;top:14px;right:62px;z-index:6;display:flex;flex-direction:column;gap:2px;width:46px;padding:4px;user-select:none;
   background:rgba(14,18,28,.74);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,.06);border-radius:12px;box-shadow:0 6px 22px rgba(0,0,0,.45)}
 #xtoggle .tbtn{display:flex;align-items:center;justify-content:center;width:36px;height:34px;border-radius:8px;color:#8a90a0;cursor:pointer;text-decoration:none}
 #xtoggle .tbtn:hover{background:rgba(255,255,255,.06);color:#cfd2dc}
 #xtoggle .tbtn svg{width:18px;height:18px}
 #xtoggle .tbtn input{display:none}                                  /* ซ่อน native checkbox · คง <label><input> เดิม */
 #xtoggle .tbtn:has(input:checked){color:#3b9eff;background:rgba(59,158,255,.16)}   /* active สะท้อนจาก :checked */
 #xtoggle #expBtn{color:#9ec1ff}                                     /* export = action (บนสุด) */
 #xtoggle .div{height:1px;background:rgba(255,255,255,.08);margin:3px 4px;flex:none}
 #xtoggle > .div:first-child{display:none}                           /* baked (ไม่ inject export) → ซ่อน divider บนสุด */
 #xtoggle .fgroup{display:none}
 #xtoggle .fgroup.has-focus{display:flex;flex-direction:column;align-items:center;gap:2px}   /* เผยเมื่อ focus (JS toggle .has-focus) */
 #xtoggle .fhead{font-size:8.5px;color:#7a8093;letter-spacing:.6px;text-transform:uppercase;margin-top:3px}
 #xtoggle .flab{font-size:9px;color:#7a8093;margin-top:2px}
 #xtoggle input[type=number]{width:40px;background:#0e0e12;border:1px solid #2a2d38;color:#cfd2dc;border-radius:4px;padding:2px;font-size:11px;text-align:center}
 .row.open{background:#1c1e28}
 .detail{background:#0e0e12;border-bottom:1px solid #23252e;padding:2px 12px 6px}
 .detail .dl{padding:5px 0;border-bottom:1px solid #1a1c24;font-size:12px;line-height:1.5;cursor:pointer}
 .detail .dl:hover{background:#1c1e28}
 .detail .dl:last-child{border-bottom:0}
 .detail .dl b{color:#e8eaf0}
 .detail .mut{color:#8a90a3}
 .detail .dsub{font-size:10px;color:#5a5f70;padding:6px 0 2px}
 .detail .du{font-size:11px;color:#7a8093;padding:2px 0}
</style></head>
<body>
<div id="side">
 <div id="subhead">__SUBHEAD__</div>
 <div id="stat"></div>
 <div id="ulegend" style="display:none"></div>
 <input id="search" placeholder="ค้นหาจุดเข้า (เวลา / BUY / SELL / WIN / LOSS)">
 <div id="list"></div>
</div>
<div id="main">
 <div id="bar"></div>
 <div id="xtoggle">
  <div class="div"></div>
  <label class="tbtn" title="crosshair (เส้น + readout ราคา/เวลา)"><input type="checkbox" id="xcb"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="7"/><line x1="12" y1="1" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="1" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="23" y2="12"/></svg></label>
  <label class="tbtn" title="แผง equity ใต้กราฟ (เฉพาะ dynamic viewer)"><input type="checkbox" id="ecb" checked><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 17 9 11 13 15 21 6"/></svg></label>
  <label class="tbtn" title="จุดเข้า/ออกของ run ที่ซ้อน (multi-run)"><input type="checkbox" id="dcb"><svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><circle cx="5" cy="13" r="2"/><circle cx="12" cy="8" r="2"/><circle cx="19" cy="15" r="2"/></svg></label>
  <label class="tbtn" title="focus mode (ซูมกรอบไม้)"><input type="checkbox" id="fcb"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V5a1 1 0 0 1 1-1h4M20 9V5a1 1 0 0 0-1-1h-4M4 15v4a1 1 0 0 0 1 1h4M20 15v4a1 1 0 0 1-1 1h-4"/></svg></label>
  <div class="fgroup" id="fgroup">
   <div class="div"></div>
   <label class="tbtn" title="ไม้บรรทัดวัด %เนื้อพ่อ (เฉพาะ focus)"><input type="checkbox" id="rcb" checked><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 8.5 8.5 3 21 15.5 15.5 21z"/><path d="M7 7l1.5 1.5M10.5 8.5l1.5 1.5M14 12l1.5 1.5" stroke-width="1.4"/></svg></label>
   <div class="fhead">Focus</div>
   <div class="flab">N</div><input type="number" id="iN" value="55" min="5" step="5">
   <div class="flab">ratio</div><input type="number" id="iw" value="5.5" step="0.5"><input type="number" id="ih" value="7.5" step="0.5">
  </div>
 </div>
 <canvas id="cv"></canvas>
 <canvas id="cvx"></canvas>
 <div id="tip"></div>
 <div id="help">scroll = zoom · drag = pan · คลิกรายการซ้ายเพื่อกระโดด</div>
</div>
<script>
__RENDER_JS__</script></body></html>
"""
