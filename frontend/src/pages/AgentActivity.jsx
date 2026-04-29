import { useState } from 'react'
import './AgentActivity.css'

// Import PNG characters
import analystImg from '../assets/agents/analyst.png'
import riskImg from '../assets/agents/risk_manager.png'
import weeklyImg from '../assets/agents/weekly.png'
import monthlyImg from '../assets/agents/monthly.png'
import reflectorImg from '../assets/agents/reflector.png'
import newsImg from '../assets/agents/news_agent.png'
import supervisorImg from '../assets/agents/supervisor.png'
import maintenanceImg from '../assets/agents/maintenance.png'
import notifyImg from '../assets/agents/notify.png'

const AGENTS_CONFIG = [
  // ═══ HEAD OFFICE ═══
  {
    id: 'analyst',
    name: 'Analyst Agent',
    role: 'Head Trader',
    desc: 'วิเคราะห์กราฟและตัดสินใจเทรด XAUUSD',
    model: 'Sonnet',
    color: '#ff3366',  // สีแดง
    section: 'head',
    img: analystImg,
  },

  // ═══ ANALYSIS ROOM ═══
  {
    id: 'risk_manager',
    name: 'Risk Manager',
    role: 'Risk Analyst',
    desc: 'บริหารความเสี่ยง position sizing SL/TP',
    model: 'Haiku',
    color: '#00ff88',  // สีเขียว
    section: 'desk',
    desk: '01',
    img: riskImg,
  },
  {
    id: 'weekly',
    name: 'Weekly Coach',
    role: 'Performance Analyst',
    desc: 'วิเคราะห์ผลรายสัปดาห์ ปรับกลยุทธ์',
    model: 'Sonnet',
    color: '#ff9944',  // สีส้ม
    section: 'desk',
    desk: '02',
    img: weeklyImg,
  },
  {
    id: 'reflector',
    name: 'Reflector',
    role: 'Trade Reviewer',
    desc: 'บันทึกและทบทวน trade ที่ผ่านมา',
    model: 'Python',
    color: '#4488ff',  // สีน้ำเงิน
    section: 'desk',
    desk: '03',
    img: reflectorImg,
  },

  // ═══ SUPPORT DESKS ═══
  {
    id: 'monthly',
    name: 'Strategist',
    role: 'Strategy Researcher',
    desc: 'วิจัยและพัฒนา strategy รายเดือน',
    model: 'Sonnet',
    color: '#ffdd00',  // สีเหลือง
    section: 'support',
    desk: 'LAB — OPTIMIZATION',
    img: monthlyImg,
  },
  {
    id: 'news_agent',
    name: 'News Agent',
    role: 'Sentiment Analyzer',
    desc: 'วิเคราะห์ข่าวและ sentiment ตลาด',
    model: 'Haiku',
    color: '#aa66ff',  // สีม่วง
    section: 'support',
    desk: 'NEWS DESK',
    img: newsImg,
  },
  {
    id: 'supervisor',
    name: 'Guardian',
    role: 'System Supervisor',
    desc: 'ตรวจสอบ system health และ positions',
    model: 'Python',
    color: '#ff66bb',  // สีชมพู
    section: 'support',
    desk: 'SUPERVISION',
    img: supervisorImg,
  },
  {
    id: 'maintenance',
    name: 'Maintenance',
    role: 'System Engineer',
    desc: 'ดูแล log cleanup และ health check',
    model: 'Python',
    color: '#00ddff',  // สีฟ้า
    section: 'support',
    desk: 'MAINTENANCE',
    img: maintenanceImg,
  },
  {
    id: 'notify',
    name: 'Notify Agent',
    role: 'Communications',
    desc: 'ส่ง alert และ report ผ่าน Telegram',
    model: 'Python',
    color: '#666666',  // สีเทาดำ
    section: 'support',
    desk: 'COMMUNICATIONS',
    img: notifyImg,
  },
]

export default function AgentActivity({ botState }) {
  const [selectedAgent, setSelectedAgent] = useState('analyst')

  const agentActivities = botState?.agent_logs || {}
  const selectedActivities = agentActivities[selectedAgent] || []

  // Group agents by section
  const headOffice = AGENTS_CONFIG.filter(a => a.section === 'head')
  const deskAgents = AGENTS_CONFIG.filter(a => a.section === 'desk')
  const supportAgents = AGENTS_CONFIG.filter(a => a.section === 'support')

  const selectedAgentData = AGENTS_CONFIG.find(a => a.id === selectedAgent)

  return (
    <div className="agent-activity">
      <div className="trading-floor">
        {/* HEAD OFFICE */}
        <div className="floor-section head-office">
          <div className="floor-header">
            <h2 className="floor-title">HEAD OFFICE</h2>
            <span className="floor-subtitle">Executive Decision Makers</span>
          </div>
          {headOffice.map(agent => (
            <div
              key={agent.id}
              className="head-office-card"
              style={{ '--agent-color': agent.color }}
            >
              <div className="agent-char-large-wrap">
                <img
                  src={agent.img}
                  alt={agent.name}
                  className="agent-char-large"
                />
              </div>
              <div className="agent-info">
                <div className="agent-role">{agent.role}</div>
                <h3 className="agent-name">{agent.name}</h3>
                <p className="agent-desc">{agent.desc}</p>
                <div className="agent-meta">
                  <span className="agent-model badge">{agent.model}</span>
                  <span className="agent-status">
                    <span className="status-dot"></span>
                    Active
                  </span>
                </div>
              </div>
              <button
                className={`agent-select-btn ${selectedAgent === agent.id ? 'selected' : ''}`}
                onClick={() => setSelectedAgent(agent.id)}
              >
                View Activity
              </button>
            </div>
          ))}
        </div>

        {/* ANALYSIS ROOM */}
        <div className="floor-section analysis-room">
          <div className="floor-header">
            <h2 className="floor-title">ANALYSIS ROOM</h2>
            <span className="floor-subtitle">Research & Strategy Team</span>
          </div>
          <div className="desk-grid">
            {deskAgents.map(agent => (
              <div
                key={agent.id}
                className={`desk-card ${selectedAgent === agent.id ? 'selected' : ''}`}
                style={{ '--agent-color': agent.color }}
                onClick={() => setSelectedAgent(agent.id)}
              >
                <div className="desk-number">DESK {agent.desk}</div>
                <div className="agent-char-medium-wrap">
                  <img
                    src={agent.img}
                    alt={agent.name}
                    className="agent-char-medium"
                  />
                </div>
                <div className="agent-role">{agent.role}</div>
                <h3 className="agent-name">{agent.name}</h3>
                <p className="agent-desc">{agent.desc}</p>
                <div className="agent-model badge">{agent.model}</div>
              </div>
            ))}
          </div>
        </div>

        {/* SUPPORT DESKS */}
        <div className="floor-section support-desks">
          <div className="floor-header">
            <h2 className="floor-title">SUPPORT DESKS</h2>
            <span className="floor-subtitle">Operations & Infrastructure</span>
          </div>
          <div className="support-grid">
            {supportAgents.map(agent => (
              <div
                key={agent.id}
                className={`support-card ${selectedAgent === agent.id ? 'selected' : ''}`}
                style={{ '--agent-color': agent.color }}
                onClick={() => setSelectedAgent(agent.id)}
              >
                <div className="desk-label">{agent.desk}</div>
                <div className="agent-char-medium-wrap">
                  <img
                    src={agent.img}
                    alt={agent.name}
                    className="agent-char-medium"
                  />
                </div>
                <div className="agent-role">{agent.role}</div>
                <h3 className="agent-name">{agent.name}</h3>
                <div className="agent-model badge">{agent.model}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Agent Detail Panel */}
      <div className="agent-detail-panel">
        <div
          className="detail-header"
          style={{ borderLeftColor: selectedAgentData?.color || '#00ff88' }}
        >
          <div className="detail-title-group">
            <div className="agent-avatar-large">
              <img
                src={selectedAgentData?.img}
                alt={selectedAgentData?.name}
                className="avatar-img"
              />
            </div>
            <div>
              <h3 className="detail-title">{selectedAgentData?.name}</h3>
              <p className="detail-subtitle">{selectedAgentData?.role} — Activity Log</p>
            </div>
          </div>
          <div className="activity-count badge info">
            {selectedActivities.length} activities
          </div>
        </div>

        <div className="activity-list">
          {selectedActivities.length > 0 ? (
            selectedActivities.map((activity, index) => (
              <div key={index} className="activity-item">
                <div className="activity-time text-muted text-mono">
                  {activity.timestamp}
                </div>
                <div className="activity-content">
                  <div className="activity-type badge success">
                    {activity.action}
                  </div>
                  <div className="activity-message">
                    {activity.message || activity.reason}
                  </div>
                  {activity.details && (
                    <pre className="activity-details text-mono">
                      {JSON.stringify(activity.details, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state text-muted">
              No activities yet for {selectedAgentData?.name}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
