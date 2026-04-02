"""
Constants และ Mappings สำหรับ Tra(i)der Phase I

ชื่อ Conditions และ Patterns แบบไทย
"""

# Condition Names (A1-A6)
CONDITION_NAMES = {
    "A1": "อัปเทรนด์",
    "A2": "ดาวน์เทรนด์",
    "A3": "ภูเขา",
    "A4": "ในกรอบขาขึ้น",
    "A5": "ในกรอบขาลง",
    "A6": "ไม่ชัด"
}

# Pattern Names (B1-B3)
PATTERN_NAMES = {
    "B1": "ไม้รวย",
    "B2": "ตามเจ้า",
    "B2s": "ตามเจ้าเฟิร์มสั้น",
    "B3": "แนวเด้ง"
}


def get_condition_name(condition_code: str) -> str:
    """
    แปลง condition code เป็นชื่อไทย

    Args:
        condition_code: "A1" - "A6"

    Returns:
        ชื่อไทยของ condition

    Examples:
        >>> get_condition_name("A1")
        'อัปเทรนด์'
        >>> get_condition_name("A3")
        'ภูเขา'
    """
    return CONDITION_NAMES.get(condition_code, condition_code)


def get_pattern_name(pattern_code: str) -> str:
    """
    แปลง pattern code เป็นชื่อไทย

    Args:
        pattern_code: "B1", "B2", "B2s", "B3"

    Returns:
        ชื่อไทยของ pattern

    Examples:
        >>> get_pattern_name("B1")
        'ไม้รวย'
        >>> get_pattern_name("B3")
        'แนวเด้ง'
    """
    return PATTERN_NAMES.get(pattern_code, pattern_code)


def get_full_condition_name(condition_code: str) -> str:
    """
    แปลง condition เป็นรูปแบบ "A1 อัปเทรนด์"

    Args:
        condition_code: "A1" - "A6"

    Returns:
        ชื่อเต็มพร้อมเลข

    Examples:
        >>> get_full_condition_name("A1")
        'A1 อัปเทรนด์'
    """
    name = CONDITION_NAMES.get(condition_code, "")
    return f"{condition_code} {name}" if name else condition_code


def get_full_pattern_name(pattern_code: str) -> str:
    """
    แปลง pattern เป็นรูปแบบ "B1 ไม้รวย"

    Args:
        pattern_code: "B1", "B2", "B2s", "B3"

    Returns:
        ชื่อเต็มพร้อมเลข

    Examples:
        >>> get_full_pattern_name("B1")
        'B1 ไม้รวย'
    """
    name = PATTERN_NAMES.get(pattern_code, "")
    return f"{pattern_code} {name}" if name else pattern_code
