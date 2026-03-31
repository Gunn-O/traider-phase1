# XAUUSD Strategy v5 - Concise (for Claude API)

## Conditions (A1-A6)
- **A1 Uptrend**: BUY only, entry at pullback, TP: ⅓/½/yod
- **A2 Downtrend**: SELL only, entry at retest, TP: ⅓/½/bottom
- **A3 Mountain**: BUY at base, TP: ⅓/½/⅞ peak
- **A4 Sideways up**: BUY lower bound, TP: opposite edge
- **A5 Sideways down**: SELL upper bound, TP: opposite edge
- **A6 Unclear**: Use B1/B3 only

## Patterns (B1-B3)
- **B1 Spike**: Large wick (≥1.5× body) at S/R + RSI extreme
- **B2 Follow**: Breakout → pullback → retest entry
- **B3 Bounce**: Price touch S/R (≥2 times) + rejection candle

## RSI Rules
- ≤25: BUY strong | 26-35: BUY | 36-44: BUY if pattern
- 45-54: SKIP (except A4/A5) | 55-65: Momentum zone
- >70: SELL at resistance

## SL/TP Calculation
- **A1/A2**: SL = wick + buffer, TP = ⅓/½/1× prev high/low
- **A3**: SL = base low - buffer, TP = ⅓/½/⅞ mountain height
- **A4/A5**: SL = outside range + buffer, TP = opposite edge
- **A6**: SL = S/R ± buffer, TP = next S/R (R:R ≥ 1:2)

## Critical Rules
1. Confidence < 0.70 = SKIP
2. R:R < 1:2 = SKIP
3. News flag = SKIP
4. RSI neutral (45-54) = SKIP (except A4/A5)
5. No pattern or unclear = SKIP always

## Output Format
```json
{
  "action": "BUY|SELL|SKIP",
  "entry": 0.0, "sl": 0.0,
  "tp1": 0.0, "tp2": 0.0, "tp3": 0.0,
  "chart_condition": "A1-A6",
  "pattern": "B1-B3 or SKIP",
  "confidence": 0.0,
  "skip_reason": "if SKIP",
  "reason": "brief explanation"
}
```
