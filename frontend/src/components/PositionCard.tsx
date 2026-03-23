// frontend/src/components/PositionCard.tsx
// Card displaying a single open trading position.
// Shows symbol, direction, entry vs current, P&L %, SL and TP levels.
// Phase 1: Renders from props — real data via React Query in Phase 5.

import { TrendingUp, TrendingDown } from 'lucide-react'

export interface Position {
  id: string
  symbol: string
  direction: 'LONG' | 'SHORT'
  entry: number
  current: number
  pnl: number       // percent
  sl: number
  tp: number
}

function fmt(n: number, digits = 0) {
  return n.toLocaleString('vi-VN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export default function PositionCard({ position: p }: { position: Position }) {
  const isLong    = p.direction === 'LONG'
  const isWinning = p.pnl >= 0
  const DirIcon   = isLong ? TrendingUp : TrendingDown

  return (
    <div className="glass-card-hover p-4">
      {/* Top row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-slate-200">{p.symbol}</span>
          <span className={`flex items-center gap-1 text-xs font-semibold px-1.5 py-0.5 rounded
                           ${isLong ? 'text-teal-400 bg-teal-400/10' : 'text-red-400 bg-red-400/10'}`}>
            <DirIcon size={11} />
            {p.direction}
          </span>
        </div>
        <span className={`text-sm font-bold mono ${isWinning ? 'pnl-positive' : 'pnl-negative'}`}>
          {isWinning ? '+' : ''}{p.pnl.toFixed(2)}%
        </span>
      </div>

      {/* Price grid */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-slate-600 mb-0.5">Entry</p>
          <p className="mono text-slate-300">{fmt(p.entry)}</p>
        </div>
        <div>
          <p className="text-slate-600 mb-0.5">Hiện tại</p>
          <p className={`mono font-medium ${isWinning ? 'pnl-positive' : 'pnl-negative'}`}>{fmt(p.current)}</p>
        </div>
        <div className="text-right">
          <p className="text-slate-600 mb-0.5">SL / TP</p>
          <p className="mono text-red-400/80">{fmt(p.sl)}</p>
          <p className="mono text-teal-400/80">{fmt(p.tp)}</p>
        </div>
      </div>

      {/* P&L bar */}
      <div className="mt-3 h-1 rounded-full overflow-hidden bg-slate-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${isWinning ? 'bg-teal-500' : 'bg-red-500'}`}
          style={{ width: `${Math.min(Math.abs(p.pnl) * 20, 100)}%` }}
        />
      </div>
    </div>
  )
}
