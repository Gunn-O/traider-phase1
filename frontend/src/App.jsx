import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useBots } from './hooks/useBots'
import { useBotState } from './hooks/useBotState'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import Dashboard from './pages/Dashboard'
import AgentActivity from './pages/AgentActivity'
import TradeHistory from './pages/TradeHistory'
import Proposals from './pages/Proposals'
import Settings from './pages/Settings'
import Backtest from './pages/Backtest'
import Strategy from './pages/Strategy'

export default function App() {
  // New multi-bot model — primary state for Dashboard + TopBar
  const { bots, isConnected, startBot, stopBot, emergencyStopAll } = useBots()

  // Legacy single-bot view — pages that haven't migrated yet (AgentActivity,
  // Proposals, Settings) consume this. Backed by /api/status which mirrors
  // the first running bot.
  const { botState } = useBotState()

  // Selection state for the "Add Bot" form in TopBar.
  const [selection, setSelection] = useState({
    tradeKind:   'simulation',
    accountType: 'cent',
    symbol:      'XAUUSDc',
    timeframe:   'M5',
    dataSource:  'auto',
  })
  const updateSelection = (patch) => setSelection(prev => ({ ...prev, ...patch }))

  return (
    <div className="app-layout">
      <Sidebar
        botState={botState}
        isConnected={isConnected}
      />
      <div className="main-wrapper">
        <TopBar
          bots={bots}
          selection={selection}
          onSelectionChange={updateSelection}
          onAddBot={startBot}
          onEmergencyStop={emergencyStopAll}
        />
        <main className="main-content">
          <Routes>
            <Route
              path="/"
              element={<Navigate to="/dashboard" replace/>}
            />
            <Route
              path="/dashboard"
              element={<Dashboard bots={bots} onStop={stopBot} selection={selection}/>}
            />
            <Route
              path="/agents"
              element={<AgentActivity botState={botState}/>}
            />
            <Route
              path="/history"
              element={<TradeHistory/>}
            />
            <Route
              path="/proposals"
              element={<Proposals botState={botState}/>}
            />
            <Route
              path="/backtest"
              element={<Backtest/>}
            />
            <Route
              path="/strategy"
              element={<Strategy/>}
            />
            <Route
              path="/settings"
              element={<Settings botState={botState}/>}
            />
          </Routes>
        </main>
      </div>
    </div>
  )
}
