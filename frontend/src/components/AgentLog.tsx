// frontend/src/components/AgentLog.tsx
// Displays the AI agent's reasoning log for recent decision cycles.
// Shows action (EXECUTE/WAIT/SKIP), confluence score, and rationale.
// Phase 1: Receives mock entries prop — real data via WebSocket in Phase 5.

import { CheckCircle, Clock, XCircle } from 'lucide-react'

export interface AgentLogEntry {
  id: string
  time: string
  action: 'EXECUTE' | 'WAIT' | 'SKIP'
  score: number
  symbol: string
  note: string
}

const ACTION_CONFIG = {
  EXECUTE: { icon: CheckCircle, color: 'text-teal-400',  bg: 'bg-teal-400/10'  },
  WAIT:    { icon: Clock,        color: 'text-amber-400', bg: 'bg-amber-400/10' },
  SKIP:    { icon: XCircle,      color: 'text-slate-500', bg: 'bg-slate-700/30' },
}

export default function AgentLog({ entries }: { entries: AgentLogEntry[] }) {
  return (
    <div className="glass-card overflow-hidden">
      <div className="space-y-0 divide-y" style={{ '--tw-divide-opacity': 1 } as React.CSSProperties}>
        {entries.map((entry) => {
          const cfg = ACTION_CONFIG[entry.action]
          const Icon = cfg.icon
          return (
            <div key={entry.id} className="px-4 py-3 flex items-start gap-3 hover:bg-white/[0.02] transition-colors">
              <div className={`mt-0.5 shrink-0 p-1 rounded-md ${cfg.bg}`}>
                <Icon size={12} className={cfg.color} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={`text-xs font-semibold ${cfg.color}`}>{entry.action}</span>
                  <span className="text-slate-300 text-xs font-medium">{entry.symbol}</span>
                  <span className="badge-low ml-auto">{entry.score.toFixed(1)}/10</span>
                </div>
                <p className="text-xs text-slate-500 truncate">{entry.note}</p>
              </div>
              <span className="text-[10px] text-slate-700 font-mono shrink-0">{entry.time}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
