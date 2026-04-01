"""
Position Tracker - Simulated Position Management

สำหรับ Phase I ที่ยังไม่มี MT5 execution จริง
ติดตามว่า position ยังเปิดอยู่หรือปิดแล้ว (hit SL/TP)
"""

from typing import Dict, List, Optional
from datetime import datetime


class Position:
    """Single position"""

    def __init__(self, signal: Dict):
        """
        สร้าง position จาก signal

        Args:
            signal: Decision dict from G3 containing:
                - action: 'BUY' | 'SELL'
                - condition: 'A1' - 'A6'
                - entry: Entry price
                - sl: Stop loss
                - tp1, tp2, tp3: Take profit levels
                - lot_size: Position size
                - timestamp: Entry time
                - trade_id: Trade ID from sheets logger (optional)
        """
        self.id = signal.get('trade_id') or f"{signal['condition']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.trade_id = self.id  # Alias for sheets integration
        self.action = signal['action']
        self.condition = signal['condition']
        self.entry = signal['entry']
        self.sl = signal['sl']
        self.tp1 = signal['tp1']
        self.tp2 = signal.get('tp2', 0)
        self.tp3 = signal.get('tp3', 0)
        self.lot_size = signal['lot_size']
        self.open_time = signal.get('timestamp', datetime.now().isoformat())
        self.close_time = None
        self.close_price = None
        self.close_reason = None
        self.pnl = 0.0
        self.is_open = True

        # Callback for when position closes
        self.on_close_callback = None

    def check_hit(self, current_price: float, current_high: float, current_low: float) -> bool:
        """
        ตรวจสอบว่าราคาปัจจุบัน hit SL/TP หรือไม่

        Args:
            current_price: ราคาปัจจุบัน (close)
            current_high: High ของ candle ปัจจุบัน
            current_low: Low ของ candle ปัจจุบัน

        Returns:
            True ถ้า hit (position ปิด), False ถ้ายังเปิดอยู่
        """
        if not self.is_open:
            return True

        if self.action == 'BUY':
            # BUY: SL ต้องต่ำกว่า entry, TP สูงกว่า entry
            # เช็คว่า candle LOW hit SL หรือไม่
            if current_low <= self.sl:
                self._close_position(self.sl, 'SL')
                return True

            # เช็คว่า candle HIGH hit TP1/TP2/TP3
            if current_high >= self.tp1:
                # Hit TP1 ก่อน (ใช้ TP1 เป็นราคาปิด)
                self._close_position(self.tp1, 'TP1')
                return True

        elif self.action == 'SELL':
            # SELL: SL ต้องสูงกว่า entry, TP ต่ำกว่า entry
            # เช็คว่า candle HIGH hit SL
            if current_high >= self.sl:
                self._close_position(self.sl, 'SL')
                return True

            # เช็คว่า candle LOW hit TP1/TP2/TP3
            if current_low <= self.tp1:
                self._close_position(self.tp1, 'TP1')
                return True

        return False

    def _close_position(self, close_price: float, reason: str):
        """ปิด position"""
        self.is_open = False
        self.close_price = close_price
        self.close_reason = reason
        self.close_time = datetime.now().isoformat()

        # คำนวณ P&L
        if self.action == 'BUY':
            self.pnl = (close_price - self.entry) * self.lot_size * 10  # $10 per point per lot
        elif self.action == 'SELL':
            self.pnl = (self.entry - close_price) * self.lot_size * 10

        # Call callback if set (for sheets logging)
        if self.on_close_callback:
            self.on_close_callback(self)

    def to_dict(self) -> Dict:
        """Export เป็น dict"""
        return {
            'id': self.id,
            'action': self.action,
            'condition': self.condition,
            'entry': self.entry,
            'sl': self.sl,
            'tp1': self.tp1,
            'tp2': self.tp2,
            'tp3': self.tp3,
            'lot_size': self.lot_size,
            'open_time': self.open_time,
            'close_time': self.close_time,
            'close_price': self.close_price,
            'close_reason': self.close_reason,
            'pnl': self.pnl,
            'is_open': self.is_open
        }


class PositionTracker:
    """
    Position Tracker - จัดการ open positions

    ใช้ใน Phase I เพื่อ simulate position management
    """

    def __init__(self, max_total_positions: int = 2):
        """
        Initialize tracker

        Args:
            max_total_positions: จำนวน position สูงสุดที่เปิดพร้อมกันได้
        """
        self.max_total_positions = max_total_positions
        self.positions: List[Position] = []
        self.open_positions: List[Position] = []
        self.closed_positions: List[Position] = []

    def can_open_new(self, condition: str) -> bool:
        """
        เช็คว่าเปิด position ใหม่ได้หรือไม่

        Args:
            condition: Condition ที่จะเปิด (A1-A6)

        Returns:
            True ถ้าเปิดได้
        """
        # เช็คจำนวน position ทั้งหมด
        if len(self.open_positions) >= self.max_total_positions:
            return False

        # เช็คว่ามี position ของ condition นี้เปิดอยู่หรือไม่
        for pos in self.open_positions:
            if pos.condition == condition:
                return False

        return True

    def add_position(self, signal: Dict) -> Optional[Position]:
        """
        เปิด position ใหม่

        Args:
            signal: Signal dict from G3

        Returns:
            Position object ถ้าเปิดสำเร็จ, None ถ้าเปิดไม่ได้
        """
        condition = signal.get('condition', '')

        if not self.can_open_new(condition):
            return None

        position = Position(signal)
        self.positions.append(position)
        self.open_positions.append(position)

        return position

    def update_positions(self, current_price: float, current_high: float, current_low: float):
        """
        Update positions ด้วยราคาปัจจุบัน (เช็ค SL/TP hit)

        Args:
            current_price: ราคาปัจจุบัน (close)
            current_high: High ของ candle ปัจจุบัน
            current_low: Low ของ candle ปัจจุบัน
        """
        closed_this_update = []

        for pos in self.open_positions:
            if pos.check_hit(current_price, current_high, current_low):
                # Position hit SL/TP
                closed_this_update.append(pos)
                self.closed_positions.append(pos)

        # ลบ positions ที่ปิดออกจาก open_positions
        for pos in closed_this_update:
            self.open_positions.remove(pos)

        # Log ถ้ามี position ปิด
        for pos in closed_this_update:
            print(f"   🔔 Position CLOSED: {pos.condition} {pos.action}")
            print(f"      {pos.close_reason} @ ${pos.close_price:.2f}")
            print(f"      P&L: ${pos.pnl:,.2f}")

    def get_open_conditions(self) -> List[str]:
        """
        ดึง list ของ conditions ที่มี position เปิดอยู่

        Returns:
            List of condition strings (e.g., ['A3', 'A4'])
        """
        return [pos.condition for pos in self.open_positions]

    def get_summary(self) -> Dict:
        """
        สรุปสถานะ positions

        Returns:
            Dict containing summary stats
        """
        total_pnl = sum(pos.pnl for pos in self.closed_positions)
        wins = len([p for p in self.closed_positions if p.pnl > 0])
        losses = len([p for p in self.closed_positions if p.pnl < 0])

        return {
            'open_positions': len(self.open_positions),
            'closed_positions': len(self.closed_positions),
            'total_trades': len(self.positions),
            'total_pnl': total_pnl,
            'wins': wins,
            'losses': losses,
            'win_rate': (wins / len(self.closed_positions) * 100) if self.closed_positions else 0,
            'open_conditions': self.get_open_conditions()
        }


# Example usage
if __name__ == "__main__":
    print("="*70)
    print("POSITION TRACKER TEST")
    print("="*70)

    tracker = PositionTracker(max_total_positions=2)

    # Test signal 1 - BUY A3
    signal1 = {
        'action': 'BUY',
        'condition': 'A3',
        'entry': 4720.0,
        'sl': 4710.0,
        'tp1': 4750.0,
        'tp2': 4760.0,
        'tp3': 4770.0,
        'lot_size': 0.5,
        'timestamp': datetime.now().isoformat()
    }

    # Test signal 2 - BUY A4
    signal2 = {
        'action': 'BUY',
        'condition': 'A4',
        'entry': 4715.0,
        'sl': 4705.0,
        'tp1': 4740.0,
        'tp2': 4750.0,
        'tp3': 4760.0,
        'lot_size': 0.3,
        'timestamp': datetime.now().isoformat()
    }

    print("\n1. เปิด position A3...")
    pos1 = tracker.add_position(signal1)
    print(f"   ✓ Opened: {pos1.id}")

    print("\n2. เปิด position A4...")
    pos2 = tracker.add_position(signal2)
    print(f"   ✓ Opened: {pos2.id}")

    print("\n3. ลองเปิด A3 ซ้ำ (ควรถูกบล็อค)...")
    can_open = tracker.can_open_new('A3')
    print(f"   Can open A3 again? {can_open}")

    print("\n4. Update positions (price = 4730, high = 4735, low = 4725)...")
    tracker.update_positions(4730.0, 4735.0, 4725.0)

    print("\n5. Update positions (price = 4750, high = 4755, low = 4745) → hit TP1...")
    tracker.update_positions(4750.0, 4755.0, 4745.0)

    print("\n6. Summary:")
    summary = tracker.get_summary()
    for key, value in summary.items():
        print(f"   {key}: {value}")

    print("\n" + "="*70)
