import { useState } from 'react'
import { Pill } from './ui/primitives'
import { fmtTime } from '../utils/format'

// RunningBotsTable — lists every bot (running + stopped) with a per-bot Stop
// button, restoring the control the redesign had dropped. Themed to .data-table.
export default function RunningBotsTable({ bots = [], onStop, filterBotId = '', onFilterChange }) {
  const [busyId, setBusyId] = useState('')

  const handleStop = async (botId) => {
    if (!confirm(`Stop bot ${botId}?`)) return
    setBusyId(botId)
    try { await onStop?.(botId) } finally { setBusyId('') }
  }

  const sorted = [...bots].sort((a, b) => {
    if (a.status !== b.status) return a.status === 'running' ? -1 : 1
    return (a.bot_id || '').localeCompare(b.bot_id || '')
  })

  return (
    <div>
      {bots.length > 0 && onFilterChange && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          <button className={`tf-tab ${filterBotId === '' ? 'active' : ''}`} onClick={() => onFilterChange('')}>All ({bots.length})</button>
          {bots.map((b) => (
            <button key={b.bot_id} className={`tf-tab ${filterBotId === b.bot_id ? 'active' : ''}`} onClick={() => onFilterChange(b.bot_id)}>
              {b.bot_id}
            </button>
          ))}
        </div>
      )}
      {bots.length === 0 ? (
        <div className="empty-state">No bots — pick a TF and click + Add Bot</div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>BOT</th><th>TF</th><th>MODE</th><th>STATUS</th><th>PID</th>
              <th>STARTED</th><th>CYCLES</th><th>OPEN</th><th>CLOSED</th><th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((b) => (
              <tr key={b.bot_id}>
                <td className="mono">{b.bot_id}</td>
                <td className="mono">{b.tf}</td>
                <td><Pill tone="gold">{b.mode}</Pill></td>
                <td><Pill tone={b.status === 'running' ? 'green' : 'red'} solid={b.status === 'running'}>{b.status === 'running' ? 'ACTIVE' : 'STOPPED'}</Pill></td>
                <td className="mono dim">{b.bot_pid ?? '—'}</td>
                <td className="mono dim">{fmtTime(b.started_at)}</td>
                <td className="mono">{b.cycle_count ?? 0}</td>
                <td className="mono">{(b.open_orders || []).length}</td>
                <td className="mono dim">{(b.closed_orders || []).length}</td>
                <td>
                  {b.status === 'running' && (
                    <button className="btn-mini" onClick={() => handleStop(b.bot_id)} disabled={busyId === b.bot_id}>
                      {busyId === b.bot_id ? '…' : 'STOP'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
