// frontend/src/pages/Signals.tsx
// Signal feed page: lists active scan results with confluence scores.
// Color coded: teal >= 6, amber 4-5, grey < 4.
// Phase 1: Stub with mock data — real signals from backend in Phase 5.

import { Zap, TrendingUp, TrendingDown, Clock } from 'lucide-react'

// ── Mock signals ──────────────────────────────────────────────────────────────
const MOCK_SIGNALS = [
  { id: '1', symbol: 'VN30F2406', strategy: 'ORB',              direction: 'LONG',  score: 7.8, entry: 1251.0, sl: 1235.0, tp: [1270.0, 1290.0], regime: 'TRENDING_UP',   time: '09:31:00', status: 'EXECUTE' },
  { id: '2', symbol: 'HPG',       strategy: 'Trend Following',  direction: 'LONG',  score: 6.4, entry: 28200,  sl: 27100,  tp: [29800, 31000],   regime: 'TRENDING_UP',   time: '10:15:22', status: 'EXECUTE' },
  { id: '3', symbol: 'VCB',       strategy: 'VWAP Reversion',   direction: 'SHORT', score: 4.9, entry: 87500,  sl: 88800,  tp: [86200, 85000],   regime: 'RANGING',       time: '11:02:45', status: 'WAIT'    },
  { id: '4', symbol: 'BID',       strategy: 'Liquidity Hunt',   direction: 'LONG',  score: 3.1, entry: 45200,  sl: 44100,  tp: [46800, 48000],   regime: 'RANGING',       time: '13:40:11', status: 'SKIP'    },
  { id: '5', symbol: 'HPG/HSG',   strategy: 'Stat Arb',         direction: 'LONG',  score: 6.2, entry: 0,      sl: 0,      tp: [],               regime: 'RANGING',       time: '14:00:00', status: 'EXECUTE' },
]

function scoreBadge(score: number) {
  if (score >= 6) return 'badge-high'
  if (score >= 4) return 'badge-mid'
  return 'badge-low'
}

function statusColor(status: string) {
  if (status === 'EXECUTE') return 'text-teal-400'
  if (status === 'WAIT')    return 'text-amber-400'
  return 'text-slate-500'
}

export default function Signals() {
  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-slate-200">Signal Feed</h1>
        <p className="text-xs text-slate-500 mt-0.5">Realtime strategy scan results — updated every 30s</p>
      </div>

      {/* Legend */}
      <div className="flex gap-4 text-xs text-slate-500">
        <span><span className="badge-high mr-1">≥ 6</span> Execute</span>
        <span><span className="badge-mid mr-1">4–5</span> Wait</span>
        <span><span className="badge-low mr-1">&lt; 4</span> Skip</span>
      </div>

      {/* Signal table */}
      <div className="glass-card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b" style={{ borderColor: 'rgba(45,212,191,0.08)' }}>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Symbol</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Strategy</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Dir</th>
              <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Score</th>
              <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Entry</th>
              <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">SL</th>
              <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Status</th>
              <th className="text-right px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">Time</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_SIGNALS.map((sig) => (
              <tr key={sig.id} className="table-row-hover border-b" style={{ borderColor: 'rgba(45,212,191,0.04)' }}>
                <td className="px-4 py-3 font-semibold text-slate-200">{sig.symbol}</td>
                <td className="px-4 py-3 text-slate-400">{sig.strategy}</td>
                <td className="px-4 py-3">
                  {sig.direction === 'LONG'
                    ? <span className="flex items-center gap-1 text-teal-400"><TrendingUp size={14} />LONG</span>
                    : <span className="flex items-center gap-1 text-red-400"><TrendingDown size={14} />SHORT</span>
                  }
                </td>
                <td className="px-4 py-3 text-right">
                  <span className={scoreBadge(sig.score)}>{sig.score.toFixed(1)}/10</span>
                </td>
                <td className="px-4 py-3 text-right mono text-slate-300">{sig.entry.toLocaleString('vi-VN')}</td>
                <td className="px-4 py-3 text-right mono text-red-400">{sig.sl.toLocaleString('vi-VN')}</td>
                <td className={`px-4 py-3 text-right font-semibold ${statusColor(sig.status)}`}>{sig.status}</td>
                <td className="px-4 py-3 text-right text-slate-600 font-mono text-xs">{sig.time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-slate-700 text-center">
        Full signal detail panel with click-to-expand implemented in Phase 5
      </p>
    </div>
  )
}
