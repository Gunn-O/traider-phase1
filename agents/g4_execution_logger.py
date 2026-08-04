"""
G4 Execution Quality Logger — บันทึก "คุณภาพ execution" แยกจาก trade log ปกติ

เป้าหมาย: สร้าง baseline ตรวจจับการเปลี่ยนพฤติกรรมของโบรกเกอร์ (เช่น B-book → A-book:
slippage เพิ่ม, requote บ่อยขึ้น, fill ช้าลง).

ตัววัด 5 ตัว:
  1. Slippage      — requested price vs filled price (signed: + เสียเปรียบ / − ได้เปรียบ)
  2. Rejection rate — % ที่โดน reject/requote (retcode 10004/10006/10012/10015)
  3. Fill time      — latency ms จาก order_send ถึงได้ result (time.perf_counter)
  4. Spread ตอนยิง   — ask−bid ณ วินาทีส่งคำสั่ง (mt5.symbol_info_tick)
  5. ความสมมาตร     — slippage ฝั่งเสียเปรียบ vs ได้เปรียบ (count + mean แยกฝั่ง)

หลักการ: เก็บ spread คู่กับ slippage เสมอ — แยก "ตลาดผันผวน" (spread กว้างทั้งตลาด)
ออกจาก "เราโดนปฏิบัติต่างไป" (spread ปกติแต่ slippage เพิ่ม).

Storage: JSONL รายเดือน logs/execution/exec_YYYY-MM.jsonl (append-only, ensure_ascii=False).
ไม่พึ่ง Google Sheets — baseline ต้องอยู่รอด local.

Public API (4 ตัว):
  send_order_with_logging(mt5, request, meta) -> result   # ครอบ order_send ขาเข้า
  log_close_execution(mt5, position_meta, expected_price, actual_price, close_type)
  log_paper_snapshot(meta, spread_pip=None, bid=None, ask=None)
  summarize(months=None) -> dict

กฎเหล็ก: ทุก log call ต้องอยู่ใน try/except — ห้ามทำ order ล้มเหลว. stdlib เท่านั้น.
"""

import os
import json
import time
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

# 1 pip = 0.01 USD (นิยามระบบ — XAUUSD family)
PIP = 0.01

# retcode ที่นับเป็น reject / requote (MT5 TRADE_RETCODE_*)
#   10004 = REQUOTE, 10006 = REJECT, 10012 = TIMEOUT (no fill), 10015 = INVALID_PRICE
REJECT_RETCODES = frozenset({10004, 10006, 10012, 10015})

_DEFAULT_LOG_DIR = "logs/execution"


# ---------------------------------------------------------------- internals

def _enabled() -> bool:
    """อ่าน env ทุกครั้ง (dotenv โหลดแล้วใน main.py) — ปิดได้ด้วย EXECUTION_LOG_ENABLED=false"""
    return os.getenv("EXECUTION_LOG_ENABLED", "true").strip().lower() == "true"


def _log_dir() -> Path:
    return Path(os.getenv("EXECUTION_LOG_DIR", _DEFAULT_LOG_DIR))


def _month_path(dt: Optional[datetime] = None) -> Path:
    """ไฟล์ log รายเดือน keyed by wall-clock month (execution เกิดจริง ณ wall time)"""
    dt = dt or datetime.now(timezone.utc)
    return _log_dir() / f"exec_{dt:%Y-%m}.jsonl"


def _iso(v) -> Optional[str]:
    """แปลง candle_time (datetime | str | None) → ISO string อย่างปลอดภัย"""
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    return str(v)


def _append(record: dict) -> None:
    """เขียน 1 record ลง JSONL รายเดือน — ห้าม raise (disk เต็ม ฯลฯ = order ต้องไปต่อ)"""
    if not _enabled():
        return
    try:
        record.setdefault("wall_time", datetime.now(timezone.utc).isoformat())
        path = _month_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:  # pragma: no cover — defensive
        print(f"[exec_logger] WARN: failed to append execution record: {e}")


def _spread_from_tick(mt5, symbol):
    """คืน (bid, ask, spread_pip) จาก symbol_info_tick — คืน None ทั้งหมดถ้าดึงไม่ได้"""
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return (None, None, None)
        bid = float(tick.bid)
        ask = float(tick.ask)
        return (bid, ask, round((ask - bid) / PIP, 2))
    except Exception:
        return (None, None, None)


def _entry_slippage_pip(direction: Optional[str], requested: Optional[float],
                        filled: Optional[float]) -> Optional[float]:
    """Slippage ขาเข้า (signed): + = เสียเปรียบ, − = ได้เปรียบ.
      BUY  filled สูงกว่า requested → จ่ายแพงกว่า = เสียเปรียบ (+)
      SELL filled สูงกว่า requested → ขายได้แพงกว่า = ได้เปรียบ (−)
    """
    if requested is None or filled is None:
        return None
    raw = (filled - requested) / PIP
    slip = raw if (direction or "").upper() == "BUY" else -raw
    return round(slip, 2)


def _close_slippage_pip(direction: Optional[str], expected: Optional[float],
                        actual: Optional[float]) -> Optional[float]:
    """Slippage ขาออก (signed): + = เสียเปรียบ, − = ได้เปรียบ.
    ปิด BUY = ขายออก → ได้ต่ำกว่าคาด = เสียเปรียบ (+)
    ปิด SELL = ซื้อคืน → จ่ายสูงกว่าคาด = เสียเปรียบ (+)
    """
    if expected is None or actual is None:
        return None
    raw = (expected - actual) / PIP  # BUY convention: actual ต่ำกว่า expected → บวก
    slip = raw if (direction or "").upper() == "BUY" else -raw
    return round(slip, 2)


# ---------------------------------------------------------------- public API

def send_order_with_logging(mt5, request: dict, meta: Optional[dict] = None):
    """ครอบ mt5.order_send() — วัด latency, retcode, slippage, spread ตอนยิง.

    Args:
        mt5:     MetaTrader5 module
        request: dict เดียวกับที่จะส่ง mt5.order_send()
        meta:    {plan_id, trade_id, direction, candle_time, mode} (optional)

    Returns:
        result object เดิมของ MT5 — ไม่เปลี่ยน behavior ของ caller.

    การ log อยู่ใน try/except ทั้งหมด — ถ้า log พัง order ยังไปต่อได้ปกติ.
    order_send เองเรียกตรงๆ (เหมือน caller เดิม) เพื่อรักษา behavior เป๊ะ.
    """
    meta = meta or {}
    symbol = request.get("symbol")
    direction = meta.get("direction")
    requested_price = request.get("price")

    # spread ณ วินาทีส่งคำสั่ง (ก่อนยิง) — try/except ในตัว
    bid = ask = spread_pip = None
    try:
        bid, ask, spread_pip = _spread_from_tick(mt5, symbol)
    except Exception:
        pass

    # ── ยิงจริง — วัด latency ครอบเฉพาะ order_send ──
    t0 = time.perf_counter()
    result = mt5.order_send(request)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    # ── log (ห้าม raise) ──
    try:
        retcode = getattr(result, "retcode", None)
        filled_price = getattr(result, "price", None)
        try:
            filled_price = float(filled_price) if filled_price else None
        except Exception:
            filled_price = None
        rejected = retcode in REJECT_RETCODES
        slippage_pip = None
        if not rejected:
            slippage_pip = _entry_slippage_pip(direction, requested_price, filled_price)

        _append({
            "event":           "order_send",
            "mode":            meta.get("mode"),
            "candle_time":     _iso(meta.get("candle_time")),
            "symbol":          symbol,
            "plan_id":         meta.get("plan_id"),
            "trade_id":        meta.get("trade_id"),
            "direction":       direction,
            "order_action":    request.get("action"),
            "volume":          request.get("volume"),
            "requested_price": requested_price,
            "filled_price":    filled_price,
            "retcode":         retcode,
            "rejected":        bool(rejected),
            "slippage_pip":    slippage_pip,
            "spread_pip":      spread_pip,
            "bid":             bid,
            "ask":             ask,
            "latency_ms":      latency_ms,
        })
    except Exception as e:
        print(f"[exec_logger] WARN: order_send logging failed (order OK): {e}")

    return result


def log_close_execution(mt5, position_meta: dict, expected_price: Optional[float],
                        actual_price: Optional[float], close_type: str) -> None:
    """เรียกตอนไม้ปิด (เฉพาะ mode ที่มี execution จริง — micro/live).

    Args:
        mt5:            MetaTrader5 module (spread ขาปิด optional)
        position_meta:  {plan_id, trade_id, direction, candle_time, mode, symbol}
        expected_price: ราคา SL/TP ที่ตั้ง (หรือราคาที่ตั้งใจปิดสำหรับ MANUAL)
        actual_price:   ราคาปิดจริงจาก MT5 (deal price)
        close_type:     'SL' | 'TP' | 'TRAIL' | 'MANUAL'
    """
    try:
        pm = position_meta or {}
        direction = pm.get("direction")
        symbol = pm.get("symbol")
        try:
            expected_price = float(expected_price) if expected_price is not None else None
        except Exception:
            expected_price = None
        try:
            actual_price = float(actual_price) if actual_price is not None else None
        except Exception:
            actual_price = None

        bid = ask = spread_pip = None
        if mt5 is not None and symbol:
            bid, ask, spread_pip = _spread_from_tick(mt5, symbol)

        _append({
            "event":          "close",
            "mode":           pm.get("mode"),
            "candle_time":    _iso(pm.get("candle_time")),
            "symbol":         symbol,
            "plan_id":        pm.get("plan_id"),
            "trade_id":       pm.get("trade_id"),
            "direction":      direction,
            "close_type":     close_type,
            "expected_price": expected_price,
            "actual_price":   actual_price,
            "slippage_pip":   _close_slippage_pip(direction, expected_price, actual_price),
            "spread_pip":     spread_pip,
            "bid":            bid,
            "ask":            ask,
        })
    except Exception as e:
        print(f"[exec_logger] WARN: close logging failed: {e}")


def log_paper_snapshot(meta: dict, spread_pip: Optional[float] = None,
                       bid: Optional[float] = None, ask: Optional[float] = None) -> None:
    """สำหรับ paper mode — ไม่มี execution จริง แต่เก็บ spread baseline ณ จุดที่ "จะยิง".

    Args:
        meta: {plan_id, candle_time, direction, entry, mode?, symbol?, trade_id?}
        spread_pip/bid/ask: จาก symbol_info_tick ถ้ามี (DATA_MODE=mt5); yfinance → None
    """
    try:
        m = meta or {}
        _append({
            "event":       "paper_signal",
            "mode":        m.get("mode", "paper"),
            "candle_time": _iso(m.get("candle_time")),
            "symbol":      m.get("symbol"),
            "plan_id":     m.get("plan_id"),
            "trade_id":    m.get("trade_id"),
            "direction":   m.get("direction"),
            "entry":       m.get("entry"),
            "spread_pip":  spread_pip,
            "bid":         bid,
            "ask":         ask,
        })
    except Exception as e:
        print(f"[exec_logger] WARN: paper snapshot logging failed: {e}")


# ---------------------------------------------------------------- summarize

def _percentile(values: List[float], p: float) -> Optional[float]:
    """percentile แบบ linear-interpolation (ไม่ต้อง import math — ใช้ int() floor)"""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return round(float(s[0]), 3)
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)              # floor (k ≥ 0 เสมอ)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return round(float(s[lo] * (1.0 - frac) + s[hi] * frac), 3)


def _mean(values: List[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(statistics.fmean(vals), 3)


def _iter_records(months: Optional[List[str]] = None):
    """อ่านทุก record จาก exec_*.jsonl (กรองด้วย months = ['YYYY-MM', ...] ถ้าระบุ)"""
    d = _log_dir()
    if not d.exists():
        return
    for path in sorted(d.glob("exec_*.jsonl")):
        tag = path.stem.replace("exec_", "")  # 'YYYY-MM'
        if months and tag not in months:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except Exception:
                        continue  # ข้าม line เสีย ไม่ให้ล้มทั้ง summarize
        except Exception:
            continue


def list_available_months() -> List[str]:
    """คืน list เดือน ['YYYY-MM', ...] ที่มีไฟล์ log อยู่จริง (ใหม่→เก่า).

    Additive helper (frontend dropdown) — ไม่แตะ logic เดิม. ปลอดภัยเมื่อไม่มี dir.
    """
    d = _log_dir()
    if not d.exists():
        return []
    months = []
    try:
        for path in d.glob("exec_*.jsonl"):
            tag = path.stem.replace("exec_", "")  # 'YYYY-MM'
            if tag:
                months.append(tag)
    except Exception:
        return []
    return sorted(set(months), reverse=True)


def summarize(months: Optional[List[str]] = None) -> dict:
    """อ่าน log ทั้งหมด → คืนสถิติ execution quality. Python-only ($0 cost).

    Args:
        months: list ['YYYY-MM', ...] — None = ทุกเดือน

    Returns:
        dict — ไม่ error แม้ไม่มี log (คืน n_orders=0 ฯลฯ)
    """
    n_orders = 0
    n_rejected = 0
    n_closes = 0
    n_paper = 0
    latencies: List[float] = []
    spreads: List[float] = []
    entry_slips: List[float] = []
    exit_slips: List[float] = []

    for rec in _iter_records(months):
        ev = rec.get("event")
        sp = rec.get("spread_pip")
        if sp is not None:
            spreads.append(sp)

        if ev == "order_send":
            n_orders += 1
            if rec.get("rejected"):
                n_rejected += 1
            lat = rec.get("latency_ms")
            if lat is not None:
                latencies.append(lat)
            slip = rec.get("slippage_pip")
            if slip is not None:
                entry_slips.append(slip)
        elif ev == "close":
            n_closes += 1
            slip = rec.get("slippage_pip")
            if slip is not None:
                exit_slips.append(slip)
        elif ev == "paper_signal":
            n_paper += 1

    # slippage asymmetry รวมทั้งขาเข้า+ขาออก (+ = เสียเปรียบ, − = ได้เปรียบ)
    all_slips = entry_slips + exit_slips
    adverse = [s for s in all_slips if s > 0]
    favorable = [s for s in all_slips if s < 0]

    rejection_rate_pct = round(100.0 * n_rejected / n_orders, 2) if n_orders else 0.0

    return {
        "months":              months,
        "n_records":           n_orders + n_closes + n_paper,
        "n_orders":            n_orders,
        "n_closes":            n_closes,
        "n_paper_signals":     n_paper,
        "n_rejected":          n_rejected,
        "rejection_rate_pct":  rejection_rate_pct,
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "n":   len(latencies),
        },
        "slippage_pip": {
            "entry": {
                "mean": _mean(entry_slips),
                "p95":  _percentile(entry_slips, 95),
                "n":    len(entry_slips),
            },
            "exit": {
                "mean": _mean(exit_slips),
                "p95":  _percentile(exit_slips, 95),
                "n":    len(exit_slips),
            },
        },
        "slippage_asymmetry": {
            "adverse_count":   len(adverse),
            "favorable_count": len(favorable),
            "adverse_mean":    _mean(adverse),
            "favorable_mean":  _mean(favorable),
        },
        "spread_pip": {
            "p50": _percentile(spreads, 50),
            "p95": _percentile(spreads, 95),
            "n":   len(spreads),
        },
    }
