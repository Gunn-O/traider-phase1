import { useMemo, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useBots } from './hooks/useBots'
import { useBotState } from './hooks/useBotState'
import { useAccount } from './hooks/useAccount'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import Login from './pages/Login'
import CommandCenter from './pages/CommandCenter'
import Office from './pages/Office'
import LiveTrade from './pages/LiveTrade'
import Alerts from './pages/Alerts'
import TradeHistory from './pages/TradeHistory'
import Proposals from './pages/Proposals'
import Settings from './pages/Settings'
import Backtest from './pages/Backtest'
import Strategy from './pages/Strategy'
import ExecutionQuality from './pages/ExecutionQuality'

export default function App() {
  // Multi-bot state (primary) + legacy single-bot state for un-migrated pages.
  const { bots, isConnected, startBot, stopBot, emergencyStopAll } = useBots()
  const { botState } = useBotState()
  const { account } = useAccount()
  const [authed, setAuthed] = useState(true)

  // Sidebar nav counts (alerts derived from events; proposals from botState).
  const counts = useMemo(() => {
    const alerts = bots.reduce((s, b) => s + (b.events || []).filter(
      (e) => ['subprocess_died', 'emergency_stopped', 'plan_cancelled', 'stopped'].includes(e.type)
    ).length, 0)
    return { alerts, proposals: botState?.proposals_pending || 0 }
  }, [bots, botState])

  if (!authed) {
    return <Login onEnter={() => setAuthed(true)} />
  }

  return (
    <div className="app">
      <Sidebar account={account} isConnected={isConnected} counts={counts} />
      <div className="main">
        <TopBar
          bots={bots}
          onAddBot={startBot}
          onEmergencyStop={emergencyStopAll}
          onExit={() => setAuthed(false)}
          alertCount={counts.alerts}
          isConnected={isConnected}
        />
        <div className="scroll-area">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<CommandCenter bots={bots} account={account} onAddBot={startBot} onStop={stopBot} isConnected={isConnected} />} />
            <Route path="/office" element={<Office bots={bots} account={account} onAddBot={startBot} />} />
            <Route path="/trade" element={<LiveTrade bots={bots} account={account} onAddBot={startBot} onEmergencyStop={emergencyStopAll} onStop={stopBot} />} />
            <Route path="/strategy" element={<Strategy />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/history" element={<TradeHistory />} />
            <Route path="/execution" element={<ExecutionQuality />} />
            <Route path="/alerts" element={<Alerts bots={bots} />} />
            <Route path="/proposals" element={<Proposals botState={botState} />} />
            <Route path="/settings" element={<Settings botState={botState} />} />
            {/* legacy alias → office */}
            <Route path="/agents" element={<Navigate to="/office" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </div>
      </div>
    </div>
  )
}
