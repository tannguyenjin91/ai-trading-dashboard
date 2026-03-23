// frontend/src/pages/Backtest.tsx
// Backtest results page: upload CSV, select strategy, view equity curve.
// Phase 1: Stub layout — upload + chart placeholder. Full implementation in Phase 5.

import { Upload, BarChart2, TrendingUp, Percent, AlertTriangle } from 'lucide-react'

const MOCK_RESULTS = {
  strategy: 'Trend Following',
  period: '2023-01-01 → 2024-01-01',
  total_trades: 124,
  win_rate: 58.1,
  profit_factor: 1.87,
  sharpe: 1.43,
  max_drawdown: -8.2,
  total_return: 34.7,
}

function MetricCard({ label, value, suffix = '', positive }: { label: string; value: number | string; suffix?: string; positive?: boolean }) {
  const numVal = typeof value === 'number' ? value : null
  const color = positive === undefined ? 'text-slate-200'
    : (numVal !== null ? (numVal >= 0) : positive) ? 'pnl-positive' : 'pnl-negative'

  return (
    <div className="glass-card p-4">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-xl font-bold mono ${color}`}>{value}{suffix}</p>
    </div>
  )
}

export default function Backtest() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold text-slate-200">Backtest</h1>
        <p className="text-xs text-slate-500 mt-0.5">Upload lịch sử và đánh giá hiệu suất chiến lược</p>
      </div>

      {/* Upload panel */}
      <div className="glass-card p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Cấu hình Backtest</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Upload CSV */}
          <div className="col-span-1">
            <label className="block text-xs text-slate-500 mb-1.5">Dữ liệu OHLCV (CSV)</label>
            <div className="border-2 border-dashed rounded-lg p-6 flex flex-col items-center gap-2 cursor-pointer transition-colors"
                 style={{ borderColor: 'rgba(45,212,191,0.2)' }}>
              <Upload size={20} className="text-teal-500/50" />
              <p className="text-xs text-slate-600">Kéo thả file CSV vào đây</p>
            </div>
          </div>
          {/* Strategy selector */}
          <div className="col-span-1">
            <label className="block text-xs text-slate-500 mb-1.5">Chiến lược</label>
            <select className="w-full px-3 py-2.5 rounded-lg text-sm text-slate-300 bg-slate-900 border cursor-pointer"
                    style={{ borderColor: 'rgba(45,212,191,0.2)' }}>
              <option>Trend Following</option>
              <option>Opening Range Breakout</option>
              <option>VWAP Reversion</option>
              <option>Liquidity Hunt</option>
              <option>Stat Arb</option>
            </select>
          </div>
          {/* Run button */}
          <div className="col-span-1 flex items-end">
            <button className="btn-primary w-full flex items-center justify-center gap-2">
              <BarChart2 size={14} />
              Chạy Backtest
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div>
        <p className="text-xs text-slate-600 mb-3">{MOCK_RESULTS.strategy} · {MOCK_RESULTS.period}</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard label="Tổng lợi nhuận"     value={MOCK_RESULTS.total_return}  suffix="%" positive />
          <MetricCard label="Win Rate"            value={MOCK_RESULTS.win_rate}      suffix="%" />
          <MetricCard label="Sharpe Ratio"        value={MOCK_RESULTS.sharpe}        />
          <MetricCard label="Max Drawdown"        value={MOCK_RESULTS.max_drawdown}  suffix="%" positive={false} />
          <MetricCard label="Profit Factor"       value={MOCK_RESULTS.profit_factor} />
          <MetricCard label="Số lệnh"             value={MOCK_RESULTS.total_trades}  />
        </div>
      </div>

      {/* Equity curve placeholder */}
      <div className="glass-card p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Equity Curve</h2>
        <div className="h-56 rounded-lg flex items-center justify-center"
             style={{ background: 'rgba(11,17,32,0.6)', border: '1px dashed rgba(45,212,191,0.12)' }}>
          <div className="text-center">
            <TrendingUp size={24} className="text-teal-500/30 mx-auto mb-2" />
            <p className="text-xs text-slate-600">Equity curve · Recharts LineChart</p>
            <p className="text-[10px] text-slate-700 mt-0.5">Implemented in Phase 5</p>
          </div>
        </div>
      </div>
    </div>
  )
}
