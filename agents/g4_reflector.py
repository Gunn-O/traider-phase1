"""
G4 Reflector (Phase II — Python-only, $0 cost)

เดิม g4_reflector ถูกลบใน Phase I cleanup (ใช้ Claude per-day). ตัวนี้กลับมาแบบ
**Python-only ไม่มี AI** — หน้าที่เดียวคือแนบ "execution quality summary" เข้า
daily report + แจ้งเตือนเบื้องต้นเมื่อ execution เปลี่ยนบุคลิก (Phase II กฎเหล็ก:
ห้าม Claude ใน per-trade/daily pipeline — AI เฉพาะ Weekly/Monthly).

ใช้ข้อมูลจาก agents/g4_execution_logger.summarize() ล้วน. ไม่เรียก API ใดๆ.
"""

import logging
from typing import Optional, List

from agents.g4_execution_logger import summarize as _exec_summarize

logger = logging.getLogger(__name__)

# เกณฑ์ alert (Python-only — log warning เฉยๆ ยังไม่หยุดบอท)
_MIN_SAMPLE = 30          # sample < 30 orders → ยังสรุปไม่ได้ ไม่ alert
_REJECT_WARN_PCT = 5.0    # rejection_rate_pct > 5 → WARN
_ASYMMETRY_FACTOR = 3     # adverse_count > favorable_count × 3 → WARN


def should_run_daily(last_daily_date, current_date) -> bool:
    """True ถ้าข้ามวันแล้ว (mirror should_run_weekly cadence gate)."""
    if last_daily_date is None:
        return True
    try:
        return current_date > last_daily_date
    except Exception:
        return last_daily_date != current_date


def build_execution_alerts(summary: dict) -> List[str]:
    """คืน list ข้อความ alert จาก execution summary (ว่างถ้าไม่มี / sample น้อย)."""
    alerts: List[str] = []
    if not summary:
        return alerts

    n_orders = int(summary.get("n_orders", 0) or 0)
    if n_orders < _MIN_SAMPLE:
        return alerts  # ยังสรุปไม่ได้

    rej = float(summary.get("rejection_rate_pct", 0) or 0)
    if rej > _REJECT_WARN_PCT:
        alerts.append(
            f"rejection สูงผิดปกติ: {rej:.1f}% > {_REJECT_WARN_PCT}% "
            f"(n_orders={n_orders})"
        )

    asym = summary.get("slippage_asymmetry", {}) or {}
    adverse = int(asym.get("adverse_count", 0) or 0)
    favorable = int(asym.get("favorable_count", 0) or 0)
    if adverse > favorable * _ASYMMETRY_FACTOR:
        alerts.append(
            f"slippage เอียงฝั่งเสียเปรียบ — ตรวจสอบ execution "
            f"(adverse={adverse} vs favorable={favorable}, "
            f"adverse_mean={asym.get('adverse_mean')})"
        )

    return alerts


def build_daily_report(months: Optional[List[str]] = None) -> dict:
    """สร้าง daily report dict = execution summary + alerts. Python-only ($0)."""
    summary = _exec_summarize(months=months)
    alerts = build_execution_alerts(summary)
    return {
        "execution_summary": summary,
        "execution_alerts":  alerts,
    }


def log_daily_report(report: dict) -> None:
    """log execution summary + WARN alerts (ไม่หยุดบอท)."""
    try:
        summary = report.get("execution_summary", {}) or {}
        logger.info(
            "[Reflector] Execution quality (Python-only) | "
            f"n_orders={summary.get('n_orders')} "
            f"rejection={summary.get('rejection_rate_pct')}% "
            f"latency_p50={summary.get('latency_ms', {}).get('p50')}ms "
            f"slip_entry_mean={summary.get('slippage_pip', {}).get('entry', {}).get('mean')}pip "
            f"spread_p50={summary.get('spread_pip', {}).get('p50')}pip"
        )
        for msg in report.get("execution_alerts", []) or []:
            logger.warning(f"[Reflector] ⚠️ {msg}")
    except Exception as e:
        logger.warning(f"[Reflector] log_daily_report failed: {e}")
