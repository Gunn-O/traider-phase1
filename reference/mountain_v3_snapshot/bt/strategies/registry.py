# ============================================================================
# bt/strategies/registry.py
# ----------------------------------------------------------------------------
# Strategy registry — single source of truth: id (--strategy) → class
# ใช้ร่วมกัน: bt/__main__ (CLI map)
#
# ลงทะเบียนกลยุทธ์ใหม่ = เพิ่ม 1 บรรทัดใน STRATEGIES (id ตรงกับ class.name)
# *** ไม่มี logic เทรด — แค่ทะเบียนชื่อ ***
# snapshot นี้มีเฉพาะ mountain_v3
# ============================================================================
from __future__ import annotations

from bt.strategies.mountain_v3 import MountainV3

STRATEGIES = {
    MountainV3.name: MountainV3,    # "mountain_v3"
}


def strategy_ids() -> list[str]:
    """list ของ strategy id ที่ลงทะเบียน (เรียงตามลำดับลงทะเบียน)"""
    return list(STRATEGIES)
