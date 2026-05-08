import { NavLink } from 'react-router-dom'
import './Sidebar.css'

const NAV_ITEMS = [
  {
    section: 'OVERVIEW',
    items: [
      {
        path: '/dashboard',
        label: 'Dashboard',
        icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
      },
    ],
  },
  {
    section: 'TRADING',
    items: [
      {
        path: '/history',
        label: 'Trade History',
        icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01',
      },
      {
        path: '/backtest',
        label: 'Backtest',
        icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
      },
      {
        path: '/strategy',
        label: 'Strategy',
        icon: 'M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4',
      },
    ],
  },
  {
    section: 'SYSTEM',
    items: [
      {
        path: '/agents',
        label: 'Agent Activity',
        icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z',
      },
      {
        path: '/proposals',
        label: 'Proposals',
        icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
        badge: true,
      },
      {
        path: '/settings',
        label: 'Settings',
        icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z',
      },
    ],
  },
]

export default function Sidebar({ botState, isConnected }) {
  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <svg viewBox="0 0 24 24" fill="none"
             stroke="#00ff88" strokeWidth="1.5"
             width="22" height="22">
          <line x1="6"  y1="4"  x2="6"  y2="20"/>
          <line x1="12" y1="2"  x2="12" y2="22"/>
          <line x1="18" y1="6"  x2="18" y2="18"/>
          <rect x="4"  y="8"  width="4" height="6" rx="1"/>
          <rect x="10" y="5"  width="4" height="8" rx="1"/>
          <rect x="16" y="9"  width="4" height="5" rx="1"/>
        </svg>
        <div>
          <div className="logo-name">Tra(i)der</div>
          <div className="logo-sub">Phase I v2.1</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(section => (
          <div key={section.section}
               className="nav-section">
            <div className="nav-section-label">
              {section.section}
            </div>
            {section.items.map(item => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `nav-item${isActive ? ' active' : ''}`
                }
              >
                <svg viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     strokeWidth="1.5"
                     width="16" height="16">
                  <path
                    d={item.icon}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span>{item.label}</span>
                {item.badge &&
                 botState?.proposals_pending > 0 && (
                  <span className="nav-badge">
                    {botState.proposals_pending}
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className={`conn-dot ${
          isConnected ? 'online' : 'offline'
        }`}/>
        <span>{isConnected ? 'Live' : 'Offline'}</span>
        <span className="sidebar-version">v1.0</span>
      </div>
    </aside>
  )
}
