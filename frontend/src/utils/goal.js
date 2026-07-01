// goal.js — "MISSION 2026" tracker. Goal = make $3000 PROFIT (not balance).
// progress = total P/L; remaining = target − P/L (so +200 → 2800 to target,
// −200 → 3200 to target). The progress bar clamps to 0..100%.
export const GOAL_TARGET = 3000

export function computeGoal(pnl, target = GOAL_TARGET) {
  const p = Number(pnl) || 0
  const remaining = target - p
  const pct = target > 0 ? Math.max(0, Math.min(100, (p / target) * 100)) : 0
  return { target, progress: p, remaining, pct }
}

export default computeGoal
