"""
Constants และ Mappings สำหรับ Tra(i)der Phase I

Updated for v2.1:
- Chart Types: uptrend, downtrend, sideway_down, sideway_up, mountain, unclear
- Techniques: twin_candle, breakout_follow, mai_ruay, support_bounce
"""

from config import CHART_TYPES, TECHNIQUES, TIMEFRAMES, TF_SIZE

# ============================================================================
# CHART TYPE NAMES (v2.1) — ชื่อไทย
# ============================================================================

CHART_TYPE_NAMES_TH = {
    "uptrend": "เทรนขึ้น",
    "downtrend": "เทรนลง",
    "sideway_down": "ไซเวย์กดลง",
    "sideway_up": "ไซเวย์ยกขึ้น",
    "mountain": "ภูเขา",
    "unclear": "ไม่ชัด"
}

# ============================================================================
# TECHNIQUE NAMES (v2.1) — ชื่อไทย
# ============================================================================

TECHNIQUE_NAMES_TH = {
    "twin_candle": "แท่งคู่",
    "breakout_follow": "ตามเจ้า",
    "mai_ruay": "ไม้รวย",
    "support_bounce": "แนวเด้ง"
}


# ============================================================================
# OLD MAPPINGS (v1 — เก็บไว้อ้างอิง)
# ============================================================================

# # Condition Names (A1-A6) — DEPRECATED in v2.1
# CONDITION_NAMES = {
#     "A1": "อัปเทรนด์",
#     "A2": "ดาวน์เทรนด์",
#     "A3": "ภูเขา",
#     "A4": "ในกรอบขาขึ้น",
#     "A5": "ในกรอบขาลง",
#     "A6": "ไม่ชัด"
# }

# # Pattern Names (B1-B3) — DEPRECATED in v2.1
# PATTERN_NAMES = {
#     "B1": "ไม้รวย",
#     "B2": "ตามเจ้า",
#     "B2s": "ตามเจ้าเฟิร์มสั้น",
#     "B3": "แนวเด้ง"
# }


# ============================================================================
# HELPER FUNCTIONS (v2.1)
# ============================================================================

def get_chart_type_name_th(chart_type: str) -> str:
    """
    แปลง chart type เป็นชื่อไทย

    Args:
        chart_type: "uptrend" | "downtrend" | "sideway_down" | "sideway_up" | "mountain" | "unclear"

    Returns:
        ชื่อไทยของ chart type

    Examples:
        >>> get_chart_type_name_th("uptrend")
        'เทรนขึ้น'
        >>> get_chart_type_name_th("mountain")
        'ภูเขา'
    """
    return CHART_TYPE_NAMES_TH.get(chart_type, chart_type)


def get_technique_name_th(technique: str) -> str:
    """
    แปลง technique เป็นชื่อไทย

    Args:
        technique: "twin_candle" | "breakout_follow" | "mai_ruay" | "support_bounce"

    Returns:
        ชื่อไทยของ technique

    Examples:
        >>> get_technique_name_th("twin_candle")
        'แท่งคู่'
        >>> get_technique_name_th("mai_ruay")
        'ไม้รวย'
    """
    return TECHNIQUE_NAMES_TH.get(technique, technique)


def get_tf_direction(action: str) -> str:
    """
    แปลง action เป็นทิศทาง (ภาษาไทย)

    Args:
        action: "BUY" | "SELL"

    Returns:
        ทิศทางภาษาไทย

    Examples:
        >>> get_tf_direction("BUY")
        'ขึ้น'
        >>> get_tf_direction("SELL")
        'ลง'
    """
    return "ขึ้น" if action == "BUY" else "ลง" if action == "SELL" else "ไม่ทราบ"


def format_chart_summary(chart_type: str, technique: str, action: str, tf: str) -> str:
    """
    สร้าง summary ภาษาไทย

    Args:
        chart_type: Chart type (uptrend, downtrend, etc.)
        technique: Technique used
        action: BUY/SELL
        tf: Timeframe

    Returns:
        Summary string

    Example:
        >>> format_chart_summary("uptrend", "twin_candle", "BUY", "H1")
        'เทรนขึ้น → แท่งคู่ → ขึ้น (H1)'
    """
    chart_th = get_chart_type_name_th(chart_type)
    tech_th = get_technique_name_th(technique)
    dir_th = get_tf_direction(action)
    return f"{chart_th} → {tech_th} → {dir_th} ({tf})"


# ============================================================================
# OLD FUNCTIONS (v1 — DEPRECATED, เก็บไว้ backward compatibility)
# ============================================================================

# def get_condition_name(condition_code: str) -> str:
#     """DEPRECATED: ใช้ get_chart_type_name_th() แทน"""
#     old_mapping = {
#         "A1": "uptrend",
#         "A2": "downtrend",
#         "A3": "mountain",
#         "A4": "sideway_up",
#         "A5": "sideway_down",
#         "A6": "unclear"
#     }
#     chart_type = old_mapping.get(condition_code, condition_code)
#     return get_chart_type_name_th(chart_type)

# def get_pattern_name(pattern_code: str) -> str:
#     """DEPRECATED: ใช้ get_technique_name_th() แทน"""
#     old_mapping = {
#         "B1": "mai_ruay",
#         "B2": "breakout_follow",
#         "B3": "twin_candle"
#     }
#     technique = old_mapping.get(pattern_code, pattern_code)
#     return get_technique_name_th(technique)
