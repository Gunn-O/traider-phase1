import { useEffect, useState } from 'react'

// useAccount — pulls live account figures from /api/mt5-status for the sidebar
// tile and dashboard stat row. Degrades to null when MT5 isn't connected.
export function useAccount(pollMs = 5000) {
  const [account, setAccount] = useState(null)
  const [mt5, setMt5] = useState(null)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await fetch('/api/mt5-status')
        if (!r.ok) return
        const j = await r.json()
        if (!alive) return
        setMt5(j)
        const a = j.account || {}
        setAccount({
          login: a.login != null ? String(a.login) : '',
          balance: a.balance ?? null,
          equity: a.equity ?? null,
          floating: a.equity != null && a.balance != null ? a.equity - a.balance : null,
          marginUsed: a.margin ?? null,
          freeMargin: a.free_margin ?? a.margin_free ?? null,
          positions: a.positions_count ?? 0,
          connected: !!j.connected,
          // lot-base notional the bot sizes lots from (fixed, UI-editable — not equity)
          lotBase: j.lot_base_portfolio ?? null,
          lotBaseSource: j.lot_base_source ?? null,
        })
      } catch { /* ignore */ }
    }
    load()
    const t = setInterval(load, pollMs)
    return () => { alive = false; clearInterval(t) }
  }, [pollMs])

  return { account, mt5 }
}

export default useAccount
