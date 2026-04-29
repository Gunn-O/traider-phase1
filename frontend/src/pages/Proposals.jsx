import { useState, useEffect } from 'react'

export default function Proposals({ botState }) {
  const [proposals, setProposals] = useState([])

  useEffect(() => {
    fetch('/api/proposals')
      .then(r => r.json())
      .then(data => setProposals(data.proposals || []))
      .catch(console.error)
  }, [])

  const approve = async (id) => {
    await fetch(`/api/proposals/${id}/approve`,
      { method: 'POST' })
    setProposals(p => p.filter(x => x.id !== id))
  }

  const reject = async (id) => {
    await fetch(`/api/proposals/${id}/reject`,
      { method: 'POST' })
    setProposals(p => p.filter(x => x.id !== id))
  }

  return (
    <div className="page-content">
      <div className="page-header">
        <h1>Strategy Proposals</h1>
        <span className="muted">
          จาก Monthly Strategist Agent
        </span>
      </div>

      {proposals.length === 0 ? (
        <div className="empty-state">
          No pending proposals
        </div>
      ) : (
        proposals.map(p => (
          <div key={p.id} className="proposal-card">
            <div className="proposal-header">
              <span className={`priority ${p.priority}`}>
                {p.priority?.toUpperCase()}
              </span>
              <span className="rule-target">
                {p.rule_target}
              </span>
            </div>
            <div className="proposal-body">
              <div className="rule-row">
                <span className="label">Current:</span>
                <code>{p.current_rule}</code>
              </div>
              <div className="rule-row">
                <span className="label">Proposed:</span>
                <code className="proposed">
                  {p.proposed_change}
                </code>
              </div>
              <div className="evidence">
                Evidence: {p.evidence?.supporting_stat}
                ({p.evidence?.sample_size} trades)
              </div>
            </div>
            <div className="proposal-actions">
              <button
                className="btn-approve"
                onClick={() => approve(p.id)}>
                ✅ Approve
              </button>
              <button
                className="btn-reject"
                onClick={() => reject(p.id)}>
                ❌ Reject
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  )
}
