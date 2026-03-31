"""
G3a — Decision Agent (Claude API)

หน้าที่:
- รับ world_state + confidence_data จาก G2
- อ่าน Strategy MD (XAUUSD_Strategy_v5.md)
- ส่ง prompt ไปยัง Claude API
- ตัดสินใจ BUY / SELL / SKIP ตาม strategy rules
- คำนวณ Entry / SL / TP1-3

Output: decision Dict → ส่งต่อ G3b (Money Management)
"""

import os
import json
import re
from typing import Dict, Optional
import anthropic


class G3DecisionAgent:
    """
    G3a Decision Agent - ใช้ Claude API ในการตัดสินใจ

    Phase I: claude-sonnet-4-5
    Optimized: Uses concise strategy (1.5k chars) instead of full (7k chars)
    Token savings: ~70% reduction per call
    """

    # Class-level cache for strategy MD
    _strategy_cache = {}

    def __init__(self, strategy_md_path: str = None, api_key: Optional[str] = None, config: Optional[Dict] = None):
        """
        Initialize Decision Agent

        Args:
            strategy_md_path: Path to Strategy MD file (default: concise version)
            api_key: Anthropic API key (or read from env ANTHROPIC_API_KEY)
            config: Optional configuration:
                - model: Model name (default: claude-sonnet-4-5)
                - max_tokens: Max tokens (default: 1024)
                - verbose: Print debug info (default: False)
                - use_concise: Use concise strategy (default: True)
        """
        self.config = config or {}
        self.verbose = self.config.get('verbose', False)

        # Choose strategy file
        use_concise = self.config.get('use_concise', True)

        if strategy_md_path is None:
            # Auto-select based on use_concise
            if use_concise:
                strategy_md_path = 'strategy/XAUUSD_Strategy_v5_concise.md'
            else:
                strategy_md_path = 'strategy/XAUUSD_Strategy_v5.md'

        self.strategy_md_path = strategy_md_path

        # Load Strategy MD with caching
        if strategy_md_path in self._strategy_cache:
            self.strategy_md = self._strategy_cache[strategy_md_path]
            if self.verbose:
                print(f"✓ Using cached strategy MD: {len(self.strategy_md)} chars")
        else:
            if not os.path.exists(strategy_md_path):
                raise FileNotFoundError(f"Strategy MD not found: {strategy_md_path}")

            with open(strategy_md_path, 'r', encoding='utf-8') as f:
                self.strategy_md = f.read()

            # Cache it
            self._strategy_cache[strategy_md_path] = self.strategy_md

            if self.verbose:
                print(f"✓ Loaded & cached strategy MD: {len(self.strategy_md)} chars")

        # Initialize Anthropic client
        api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment or config")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = self.config.get('model', 'claude-sonnet-4-5')
        self.max_tokens = self.config.get('max_tokens', 1024)

        if self.verbose:
            print(f"✓ Anthropic client initialized (model: {self.model})")

    def decide(self, world_state: Dict, confidence_data: Dict) -> Optional[Dict]:
        """
        ตัดสินใจ BUY/SELL/SKIP ด้วย Claude API

        Args:
            world_state: Output from G1
            confidence_data: Output from G2

        Returns:
            decision Dict if action != SKIP, None if SKIP
            {
                'chart_condition': str,
                'pattern': str,
                'action': 'BUY' | 'SELL' | 'SKIP',
                'confidence': float,
                'entry': float,
                'sl': float,
                'tp1': float,
                'tp2': float,
                'tp3': float,
                'lot': float (placeholder - calculated by G3b),
                'rsi_now': float,
                'h1_trend': str,
                'session': str,
                'candles_checked': int,
                'skip_reason': str,
                'reason': str
            }
        """
        # Build prompts
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(world_state, confidence_data)

        if self.verbose:
            print(f"\n🤖 Calling Claude API...")
            print(f"   System prompt: {len(system_prompt)} chars")
            print(f"   User prompt: {len(user_prompt)} chars")

        try:
            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            # Extract text
            raw_text = response.content[0].text.strip()

            if self.verbose:
                print(f"   Response: {len(raw_text)} chars")
                print(f"\n📝 Raw response:\n{raw_text}\n")

            # Parse JSON (remove markdown if present)
            json_text = self._extract_json(raw_text)
            decision = json.loads(json_text)

            # Validate
            self._validate_decision(decision)

            # Log decision
            if self.verbose:
                print(f"\n✓ Decision: {decision['action']}")
                if decision['action'] != 'SKIP':
                    print(f"   Condition: {decision['chart_condition']}")
                    print(f"   Pattern: {decision['pattern']}")
                    print(f"   Entry: ${decision['entry']:.2f}")
                    print(f"   SL: ${decision['sl']:.2f}")
                    print(f"   TP1/2/3: ${decision['tp1']:.2f} / ${decision['tp2']:.2f} / ${decision['tp3']:.2f}")
                else:
                    print(f"   Reason: {decision['skip_reason']}")

            # Return None if SKIP
            if decision['action'] == 'SKIP':
                return None

            return decision

        except Exception as e:
            print(f"❌ Error calling Claude API: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return None

    def _build_system_prompt(self) -> str:
        """Build system prompt with Strategy MD"""
        return f"""คุณคือ XAUUSD Trading Analyst ผู้เชี่ยวชาญ

อ่าน Strategy Document ด้านล่างแล้วตัดสินใจ BUY / SELL / SKIP
ตอบเป็น JSON เท่านั้น ห้าม markdown ห้าม explanation นอก JSON

=== STRATEGY DOCUMENT (Source of Truth) ===

{self.strategy_md}

=== END STRATEGY DOCUMENT ===

กฎเพิ่มเติม:
- confidence < 0.70 = SKIP เสมอ (ส่งมาจาก G2 แล้ว)
- R:R < 1:2 = SKIP เสมอ
- news_flag = true = SKIP เสมอ
- ถ้าไม่มั่นใจหรือเงื่อนไขไม่ครบ = SKIP
- ตอบ JSON format ที่กำหนดเท่านั้น ห้าม ```json wrapper

JSON Format:
{{
  "chart_condition": "A1_uptrend | A2_downtrend | A3_mountain | A4_sideways_up | A5_sideways_down | A6_unclear",
  "pattern": "ไม้รวย | ตามเจ้า | แนวเด้ง | SKIP",
  "action": "BUY | SELL | SKIP",
  "confidence": 0.0,
  "entry": 0.0,
  "sl": 0.0,
  "tp1": 0.0,
  "tp2": 0.0,
  "tp3": 0.0,
  "lot": 0.0,
  "rsi_now": 0.0,
  "h1_trend": "bullish | bearish | sideways",
  "session": "Asia | London | NY | ...",
  "candles_checked": 80,
  "skip_reason": "ระบุเหตุผลถ้า SKIP — ว่างถ้าไม่ SKIP",
  "reason": "อธิบายสั้นๆ เงื่อนไขที่ครบ"
}}"""

    def _build_user_prompt(self, world_state: Dict, confidence_data: Dict) -> str:
        """Build user prompt with market data"""
        # Convert world_state to ensure JSON serializable
        ws_clean = {k: (str(v) if isinstance(v, bool) else v) for k, v in world_state.items()}

        return f"""วิเคราะห์ market state นี้และตัดสินใจ:

=== MARKET STATE (from G1) ===
{json.dumps(ws_clean, ensure_ascii=False, indent=2, default=str)}

=== CONFIDENCE ANALYSIS (from G2) ===
Confidence: {confidence_data['confidence']:.3f}
RSI Score: {confidence_data['rsi_score']:.3f}
S/R Score: {confidence_data['sr_score']:.3f}
Trend Score: {confidence_data['trend_score']:.3f}
Breakdown: {confidence_data['breakdown']}

=== INSTRUCTIONS ===
1. อ่าน Strategy Document ข้างต้น
2. ตรวจสอบว่า Condition และ Pattern ตรงกับ rules หรือไม่
3. ถ้าครบเงื่อนไข → คำนวณ Entry, SL, TP1-3 ตาม Strategy
4. ถ้าไม่ครบหรือไม่มั่นใจ → SKIP พร้อมระบุเหตุผล
5. ตรวจสอบ R:R ≥ 1:2 ก่อน approve

ตอบเป็น JSON เท่านั้น (ห้าม markdown wrapper):"""

    def _extract_json(self, text: str) -> str:
        """Extract JSON from response (remove markdown if present)"""
        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*$', '', text)
        text = text.strip()
        return text

    def _validate_decision(self, decision: Dict):
        """Validate decision dict"""
        required_fields = [
            'chart_condition', 'pattern', 'action', 'confidence',
            'entry', 'sl', 'tp1', 'tp2', 'tp3', 'lot',
            'rsi_now', 'h1_trend', 'session', 'candles_checked',
            'skip_reason', 'reason'
        ]

        for field in required_fields:
            if field not in decision:
                raise ValueError(f"Missing required field: {field}")

        # Validate action
        if decision['action'] not in ['BUY', 'SELL', 'SKIP']:
            raise ValueError(f"Invalid action: {decision['action']}")

        # Validate confidence
        if not (0.0 <= decision['confidence'] <= 1.0):
            raise ValueError(f"Invalid confidence: {decision['confidence']}")

        # Validate prices if not SKIP
        if decision['action'] != 'SKIP':
            if decision['entry'] <= 0:
                raise ValueError(f"Invalid entry: {decision['entry']}")
            if decision['sl'] <= 0:
                raise ValueError(f"Invalid SL: {decision['sl']}")
            if decision['tp1'] <= 0 or decision['tp2'] <= 0 or decision['tp3'] <= 0:
                raise ValueError("Invalid TP values")


# Convenience function
def get_decision(world_state: Dict, confidence_data: Dict,
                strategy_md_path: str = 'strategy/XAUUSD_Strategy_v5.md',
                config: Optional[Dict] = None) -> Optional[Dict]:
    """
    Convenience function to get decision

    Args:
        world_state: From G1
        confidence_data: From G2
        strategy_md_path: Path to strategy MD
        config: Optional config

    Returns:
        Decision dict or None if SKIP
    """
    agent = G3DecisionAgent(strategy_md_path, config=config)
    return agent.decide(world_state, confidence_data)


# Example usage
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    print("="*70)
    print("G3a DECISION AGENT TEST")
    print("="*70)

    # Mock data for testing
    mock_world_state = {
        'symbol': 'XAUUSD',
        'price': 3050.48,
        'rsi': 36.2,
        'rsi_zone': 'near_oversold',
        'h1_trend': 'bullish',
        'condition_candidate': 'A3_mountain',
        'pattern_candidate': 'แนวเด้ง',
        'nearest_sr': 3050.00,
        'sr_distance': 0.48,
        'sr_touches': 3,
        'sr_type': 'support',
        'sr_strength': 0.92,
        'spike_detected': False,
        'spike_ratio': 0.0,
        'news_flag': False,
        'news_event': '',
        'session': 'London',
        'spread_ok': True,
        'candles_checked': 80,
        'timestamp': '2025-03-15T10:30:00Z'
    }

    mock_confidence = {
        'confidence': 0.862,
        'filter_pass': True,
        'rsi_score': 0.700,
        'sr_score': 0.880,
        'trend_score': 1.000,
        'breakdown': 'RSI 36.2 (near_oversold), S/R 3 touches at $3050.00, H1 bullish aligned with A3_mountain'
    }

    print(f"\n📊 Testing with mock data...")
    print(f"   Condition: {mock_world_state['condition_candidate']}")
    print(f"   Pattern: {mock_world_state['pattern_candidate']}")
    print(f"   RSI: {mock_world_state['rsi']} ({mock_world_state['rsi_zone']})")
    print(f"   Confidence: {mock_confidence['confidence']:.3f}")

    # Initialize agent
    agent = G3DecisionAgent(
        strategy_md_path='strategy/XAUUSD_Strategy_v5.md',
        config={'verbose': True}
    )

    # Get decision
    decision = agent.decide(mock_world_state, mock_confidence)

    if decision:
        print(f"\n✅ Decision received!")
        print(json.dumps(decision, indent=2, ensure_ascii=False))
    else:
        print(f"\n⏭  Claude decided to SKIP")

    print("\n" + "="*70)
