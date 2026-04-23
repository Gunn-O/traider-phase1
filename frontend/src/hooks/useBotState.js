import { useState, useEffect } from 'react'
import { useWebSocket } from './useWebSocket'

const DEFAULT_STATE = {
  status: 'stopped',
  mode: 'paper',
  symbol: 'XAUUSDm',
  trading_tf: 'M5',
  data_source_actual: '',
  current_price: 0,
  balance: 0,
  daily_pnl: 0,
  total_pnl: 0,
  win: 0,
  loss: 0,
  consecutive_loss: 0,
  open_orders: [],
  last_decision: {},
  last_reflection: '',
  agent_logs: {
    analyst: [],
    risk_manager: [],
    weekly: [],
    monthly: [],
    reflector: [],
  },
  logs: [],
  proposals_pending: 0,
}

export function useBotState() {
  const [botState, setBotState] = useState(DEFAULT_STATE)
  // ไม่ต้องส่ง URL — useWebSocket จัดการเอง
  const { data, isConnected } = useWebSocket()

  useEffect(() => {
    if (data) {
      setBotState(prev => ({ ...prev, ...data }))
    }
  }, [data])

  const startBot = async (config) => {
    try {
      const res = await fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      if (!res.ok) throw new Error(await res.text())
    } catch (err) {
      console.error('Start bot error:', err)
    }
  }

  const stopBot = async () => {
    try {
      await fetch('/api/stop', { method: 'POST' })
    } catch (err) {
      console.error('Stop bot error:', err)
    }
  }

  const emergencyStop = async () => {
    if (!confirm('🚨 Emergency Stop\nปิดทุก order ทันที ยืนยันไหม?')) return
    try {
      await fetch('/api/emergency-stop', { method: 'POST' })
    } catch (err) {
      console.error('Emergency stop error:', err)
    }
  }

  return {
    botState,
    isConnected,
    startBot,
    stopBot,
    emergencyStop,
  }
}
