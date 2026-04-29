import { Routes, Route, Navigate } from 'react-router-dom'
import { useBotState } from './hooks/useBotState'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import Dashboard from './pages/Dashboard'
import AgentActivity from './pages/AgentActivity'
import TradeHistory from './pages/TradeHistory'
import Proposals from './pages/Proposals'
import Settings from './pages/Settings'
import Backtest from './pages/Backtest'

export default function App() {
  const {
    botState, isConnected,
    startBot, stopBot, emergencyStop
  } = useBotState()

  return (
    <div className="app-layout">
      <Sidebar
        botState={botState}
        isConnected={isConnected}
      />
      <div className="main-wrapper">
        <TopBar
          botState={botState}
          onStart={startBot}
          onStop={stopBot}
          onEmergencyStop={emergencyStop}
        />
        <main className="main-content">
          <Routes>
            <Route
              path="/"
              element={<Navigate to="/dashboard" replace/>}
            />
            <Route
              path="/dashboard"
              element={<Dashboard botState={botState}/>}
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
              path="/settings"
              element={<Settings botState={botState}/>}
            />
          </Routes>
        </main>
      </div>
    </div>
  )
}
