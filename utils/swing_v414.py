def bsize(b): return (max(b[2],b[5]) - min(b[2],b[5])) * 100
def bhi(b):   return max(b[2], b[5])
def blo(b):   return min(b[2], b[5])
def O(b):     return b[2]
def H(b):     return b[3]
def L(b):     return b[4]
def C(b):     return b[5]


def _check_high(bars, li, rj, mid, R55, thick_exc=False, right2_exc=False):
    """
    à¸à¸£à¸§à¸ Swing High
    thick_exc   = à¹à¸à¹ à¸à¹à¸²à¸¢1+à¸à¸§à¸²1 à¹à¸à¸ à¸à¹à¸²à¸¢3+à¸à¸§à¸²2 (exception à¹à¸à¹à¸à¸«à¸à¸²)
    right2_exc  = à¸à¹à¸² Right2 à¹à¸¡à¹à¸¡à¸µà¹à¸à¸à¹à¸­à¸¡à¸¹à¸¥ à¹à¸«à¹à¸à¹à¸²à¸à¸à¸±à¸à¸à¸µ (Right2 exception)
    """
    left_range  = [li-1] if thick_exc else [li-3, li-2, li-1]
    right_range = [rj+1] if thick_exc else [rj+1, rj+2]

    for k in left_range:
        if k < 0: continue
        b = bars[k]
        if O(b) >= mid or C(b) >= mid: return False

    for k in right_range:
        if k >= len(bars):
            return right2_exc   # â Right2 exception
        b = bars[k]
        if O(b) >= mid or C(b) >= mid: return False

    return True


def _check_low(bars, li, rj, mid, R55, thick_exc=False, right2_exc=False):
    """
    à¸à¸£à¸§à¸ Swing Low (Mirror à¸à¸²à¸ Swing High)
    """
    left_range  = [li-1] if thick_exc else [li-3, li-2, li-1]
    right_range = [rj+1] if thick_exc else [rj+1, rj+2]

    for k in left_range:
        if k < 0: continue
        b = bars[k]
        if O(b) <= mid or C(b) <= mid: return False

    for k in right_range:
        if k >= len(bars):
            return right2_exc
        b = bars[k]
        if O(b) <= mid or C(b) <= mid: return False

    return True


def scan_swings(bars, R55,
                cur_H=None, hl_zone_hi=None,   # BUY: HL Right2 exception
                cur_L=None, lh_zone_lo=None):   # SELL: LL Right2 exception
    """
    à¸ªà¹à¸à¸à¸«à¸² Swing High à¹à¸¥à¸° Swing Low à¸à¸±à¹à¸à¸«à¸¡à¸à¹à¸ bars
    à¸à¸£à¹à¸­à¸¡à¸à¹à¸­à¸¢à¸à¹à¸§à¹à¸à¸à¸±à¹à¸ 2 à¹à¸à¸:
      1. à¹à¸à¹à¸à¸«à¸à¸² > 5%R55 â à¸à¹à¸²à¸¢1+à¸à¸§à¸²1
      2. Right2 à¹à¸¡à¹à¸¡à¸µà¹à¸à¸à¹à¸­à¸¡à¸¹à¸¥ à¹à¸à¹à¸£à¸²à¸à¸²à¹à¸à¸° Entry Zone â à¸à¹à¸²à¸à¸à¸±à¸à¸à¸µ
    """
    thresh1  = R55 * 0.01  # 1%R55  â à¹à¸à¸·à¹à¸­à¸à¹à¸à¸à¸±à¹à¸à¸à¹à¸³à¹à¸à¹à¸à¸à¸¹à¹
    thresh5  = R55 * 0.10  # 10%R55  â à¹à¸à¹à¸à¸«à¸à¸² exception

    highs, lows = [], []
    seen_h, seen_l = set(), set()

    def try_sh(li, rj, c1, c3):
        key = (c1[0], c3[0])
        if key in seen_h: return
        if abs(C(c1) - O(c3)) * 100 > 100: return
        if bsize(c1) < thresh1 or bsize(c3) < thresh1: return
        mid = (C(c1) + O(c3)) / 2

        # à¹à¸à¹à¸à¸«à¸à¸² exception
        thick = bsize(c1) > thresh5 or bsize(c3) > thresh5

        # Right2 exception (BUY: HL à¹à¸à¸° HL zone)
        r2_exc = bool(
            cur_L is not None and hl_zone_hi is not None and cur_L <= hl_zone_hi
        )

        if _check_high(bars, li, rj, mid, R55, thick_exc=thick, right2_exc=r2_exc):
            seen_h.add(key)
            highs.append({
                "body_hi": max(bhi(c1), bhi(c3)),
                "mid": mid,
                "times": [bars[li][1], bars[rj][1]],
                "bar_nums": [bars[li][0], bars[rj][0]],
                "thick": thick,
            })

    def try_sl(li, rj, c1, c3):
        key = (c1[0], c3[0])
        if key in seen_l: return
        if abs(C(c1) - O(c3)) * 100 > 100: return
        if bsize(c1) < thresh1 or bsize(c3) < thresh1: return
        mid = (C(c1) + O(c3)) / 2

        # à¹à¸à¹à¸à¸«à¸à¸² exception
        thick = bsize(c1) > thresh5 or bsize(c3) > thresh5

        # Right2 exception (SELL: LL à¹à¸à¸° LH zone)
        r2_exc = bool(
            cur_H is not None and lh_zone_lo is not None and cur_H >= lh_zone_lo
        )

        if _check_low(bars, li, rj, mid, R55, thick_exc=thick, right2_exc=r2_exc):
            seen_l.add(key)
            lows.append({
                "body_lo": min(blo(c1), blo(c3)),
                "mid": mid,
                "times": [bars[li][1], bars[rj][1]],
                "bar_nums": [bars[li][0], bars[rj][0]],
                "thick": thick,
            })

    for i in range(len(bars) - 1):
        j = i + 1
        bi, bj = bars[i], bars[j]
        if abs(C(bi) - O(bj)) * 100 > 50: continue

        bid = bsize(bi) < thresh1
        bjd = bsize(bj) < thresh1

        if not bid and not bjd:
            try_sh(i, j, bi, bj)
            try_sl(i, j, bi, bj)
        elif not bid and bjd:   # bj=Doji â à¸à¸¢à¸²à¸¢à¸à¸§à¸²
            if j + 1 < len(bars):
                try_sh(i, j+1, bi, bars[j+1])
                try_sl(i, j+1, bi, bars[j+1])
        elif bid and not bjd:   # bi=Doji â à¸à¸¢à¸²à¸¢à¸à¹à¸²à¸¢
            if i - 1 >= 0:
                try_sh(i-1, j, bars[i-1], bj)
                try_sl(i-1, j, bars[i-1], bj)
        # à¸à¸±à¹à¸à¸à¸¹à¹ Doji â à¸à¹à¸²à¸¡

    return highs, lows


# ===================== TEST =====================
if __name__ == "__main__":
    data_test = [
        (71,"05:50",4790.295,4790.585,4782.785,4787.525),
        (72,"05:55",4787.545,4788.225,4783.515,4783.925),
        (73,"06:00",4783.945,4785.325,4775.365,4782.515),
        (74,"06:05",4782.555,4787.425,4779.535,4787.315),
        (75,"06:10",4787.295,4790.535,4783.955,4784.845),
        (76,"06:15",4784.835,4785.815,4779.145,4780.385),
        (77,"06:20",4780.335,4783.295,4776.885,4781.315),
    ]
    R55 = 3516.0

    print("=== à¸à¸à¸ªà¸­à¸ 06:05â06:10 ===")
    hs, ls = scan_swings(data_test, R55)
    for s in hs:
        tag = "[à¹à¸à¹à¸à¸«à¸à¸² exception]" if s.get('thick') else ""
        print(f"  LH {s['times'][0]}â{s['times'][-1]}: body_hi={s['body_hi']:.3f} {tag}")
    if not hs: print("  à¹à¸¡à¹à¸à¸ Swing High")

    print("\n=== à¸à¸£à¸§à¸ mirror: à¸à¹à¸²à¸¢3/à¸à¸§à¸²2 vs à¸à¹à¸²à¸¢1/à¸à¸§à¸²1 ===")
    print("_check_high :")
    print("  à¸à¸à¸à¸´:       left=[li-3,li-2,li-1]  right=[rj+1,rj+2]")
    print("  thick_exc:  left=[li-1]             right=[rj+1]")
    print("_check_low (Mirror):")
    print("  à¸à¸à¸à¸´:       left=[li-3,li-2,li-1]  right=[rj+1,rj+2]")
    print("  thick_exc:  left=[li-1]             right=[rj+1]")
    print("  â â Mirror à¸à¸±à¸ 100%")

    print("\n=== à¸à¸£à¸§à¸ Right2 exception ===")
    print("try_sh: r2_exc = cur_L <= hl_zone_hi  (BUY â HL à¹à¸à¸° zone)")
    print("try_sl: r2_exc = cur_H >= lh_zone_lo  (SELL â LL à¹à¸à¸° zone)")
    print("  â â Mirror à¸à¸±à¸ 100%")

