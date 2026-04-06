import { useEffect, useMemo, useState } from 'react'
import { BarChart3, CalendarDays, Play, RefreshCw } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const API_BASE = 'http://localhost:8000'

interface BacktestMetrics {
  avg_trade_pnl: number
  ending_capital: number
  max_drawdown_pct: number
  net_profit: number
  profit_factor: number
  sharpe: number
  starting_capital: number
  total_return_pct: number
  total_trades: number
  win_rate: number
}

interface BacktestTrade {
  direction: 'BUY' | 'SELL'
  entry_price: number
  entry_time: string
  exit_price: number
  exit_time: string
  pnl: number
  close_reason: string
}

interface BacktestResponse {
  ended_at: string
  equity_curve: Array<{ time: string; equity: number }>
  interval: string
  metrics: BacktestMetrics
  started_at: string
  strategy: string
  symbol: string
  trades: BacktestTrade[]
}

interface StrategyOption {
  id: string
  name: string
  description: string
}

function MetricCard({
  label,
  value,
  suffix = '',
  positive,
}: {
  label: string
  value: number | string
  suffix?: string
  positive?: boolean
}) {
  const numeric = typeof value === 'number' ? value : null
  const tone =
    positive === undefined
      ? 'text-slate-200'
      : (numeric !== null ? numeric >= 0 : positive)
        ? 'text-teal-400'
        : 'text-red-400'

  return (
    <div className="glass-card p-4">
      <p className="mb-1 text-xs text-slate-500">{label}</p>
      <p className={`mono text-xl font-bold ${tone}`}>
        {typeof value === 'number' ? value.toFixed(2) : value}
        {suffix}
      </p>
    </div>
  )
}

export default function Backtest() {
  const [form, setForm] = useState({
    symbol: 'VN30F1M',
    strategy: 'mtf_signal',
    start_date: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
    end_date: new Date().toISOString().slice(0, 10),
    initial_capital: 100000000,
    min_confidence: 65,
  })
  const [strategyOptions, setStrategyOptions] = useState<StrategyOption[]>([])
  const [result, setResult] = useState<BacktestResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const response = await fetch(`${API_BASE}/v1/market/backtest-strategies`)
        if (!response.ok) return
        const payload = await response.json()
        if (!active) return
        setStrategyOptions(payload.items ?? [])
      } catch (err) {
        console.error('Failed to load backtest strategies:', err)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  const selectedStrategy = useMemo(
    () => strategyOptions.find((item) => item.id === form.strategy),
    [form.strategy, strategyOptions],
  )

  const headline = useMemo(() => {
    if (!result) return 'Replay up to 30 days of vnstock history with selectable strategy logic'
    return `${result.symbol} | ${selectedStrategy?.name || result.strategy} | ${result.started_at.slice(0, 10)} -> ${result.ended_at.slice(0, 10)}`
  }, [result, selectedStrategy])

  const runBacktest = async () => {
    try {
      setIsLoading(true)
      setError(null)
      const response = await fetch(`${API_BASE}/v1/market/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })

      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Backtest failed')
      }
      setResult(payload)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backtest failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold text-slate-200">Backtest Lab</h1>
        <p className="mt-0.5 text-xs text-slate-500">{headline}</p>
      </div>

      <div className="glass-card p-6">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-200">
          <CalendarDays size={16} className="text-teal-400" />
          Configure Replay
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-6">
          <div>
            <label className="mb-1.5 block text-xs text-slate-500">Symbol</label>
            <input
              value={form.symbol}
              onChange={(event) => setForm((prev) => ({ ...prev, symbol: event.target.value.toUpperCase() }))}
              className="w-full rounded-lg border bg-slate-900 px-3 py-2.5 text-sm text-slate-300"
              style={{ borderColor: 'rgba(45,212,191,0.12)' }}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-slate-500">Strategy</label>
            <select
              value={form.strategy}
              onChange={(event) => setForm((prev) => ({ ...prev, strategy: event.target.value }))}
              className="w-full rounded-lg border bg-slate-900 px-3 py-2.5 text-sm text-slate-300"
              style={{ borderColor: 'rgba(45,212,191,0.12)' }}
            >
              {strategyOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-slate-500">Start date</label>
            <input
              type="date"
              value={form.start_date}
              onChange={(event) => setForm((prev) => ({ ...prev, start_date: event.target.value }))}
              className="w-full rounded-lg border bg-slate-900 px-3 py-2.5 text-sm text-slate-300"
              style={{ borderColor: 'rgba(45,212,191,0.12)' }}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-slate-500">End date</label>
            <input
              type="date"
              value={form.end_date}
              onChange={(event) => setForm((prev) => ({ ...prev, end_date: event.target.value }))}
              className="w-full rounded-lg border bg-slate-900 px-3 py-2.5 text-sm text-slate-300"
              style={{ borderColor: 'rgba(45,212,191,0.12)' }}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-slate-500">Starting capital</label>
            <input
              type="number"
              value={form.initial_capital}
              onChange={(event) => setForm((prev) => ({ ...prev, initial_capital: Number(event.target.value) || 0 }))}
              className="w-full rounded-lg border bg-slate-900 px-3 py-2.5 text-sm text-slate-300"
              style={{ borderColor: 'rgba(45,212,191,0.12)' }}
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-slate-500">Min confidence</label>
            <input
              type="number"
              value={form.min_confidence}
              onChange={(event) => setForm((prev) => ({ ...prev, min_confidence: Number(event.target.value) || 0 }))}
              className="w-full rounded-lg border bg-slate-900 px-3 py-2.5 text-sm text-slate-300"
              style={{ borderColor: 'rgba(45,212,191,0.12)' }}
            />
          </div>
        </div>

        {selectedStrategy && (
          <div className="mt-4 rounded-lg border border-teal-500/10 bg-teal-500/5 px-4 py-3 text-xs text-slate-400">
            <span className="font-semibold text-teal-300">{selectedStrategy.name}:</span> {selectedStrategy.description}
          </div>
        )}

        <div className="mt-5 flex items-center gap-3">
          <button type="button" className="btn-primary flex items-center gap-2" onClick={runBacktest} disabled={isLoading}>
            {isLoading ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
            {isLoading ? 'Running...' : 'Run backtest'}
          </button>
          <p className="text-xs text-slate-500">Default window is 30 days, and you can swap strategy logic without changing the data source.</p>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs text-red-300">
          {error}
        </div>
      )}

      {result && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <MetricCard label="Net Profit" value={result.metrics.net_profit} positive />
            <MetricCard label="Return" value={result.metrics.total_return_pct} suffix="%" positive />
            <MetricCard label="Win Rate" value={result.metrics.win_rate} suffix="%" />
            <MetricCard label="Profit Factor" value={result.metrics.profit_factor} />
            <MetricCard label="Sharpe" value={result.metrics.sharpe} />
            <MetricCard label="Max Drawdown" value={result.metrics.max_drawdown_pct} suffix="%" positive={false} />
          </div>

          <div className="glass-card p-4">
            <div className="mb-3 flex items-center gap-2">
              <BarChart3 size={16} className="text-teal-400" />
              <h2 className="text-sm font-semibold text-slate-200">Equity Curve</h2>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={result.equity_curve}>
                  <CartesianGrid stroke="rgba(148, 163, 184, 0.08)" vertical={false} />
                  <XAxis
                    dataKey="time"
                    tickFormatter={(value) => value.slice(5, 16).replace('T', ' ')}
                    tick={{ fill: '#64748b', fontSize: 11 }}
                  />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={90} />
                  <Tooltip
                    formatter={(value: number) => value.toLocaleString('vi-VN', { maximumFractionDigits: 0 })}
                    labelFormatter={(value) => value}
                    contentStyle={{
                      background: 'rgba(15, 23, 42, 0.96)',
                      border: '1px solid rgba(45, 212, 191, 0.12)',
                      borderRadius: '12px',
                    }}
                  />
                  <Line type="monotone" dataKey="equity" stroke="#14b8a6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="glass-card overflow-hidden">
            <div className="border-b border-white/5 px-4 py-3">
              <h2 className="text-sm font-semibold text-slate-200">Recent Trades</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/5">
                    <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">Direction</th>
                    <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">Entry</th>
                    <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">Exit</th>
                    <th className="px-4 py-3 text-right text-xs uppercase tracking-wider text-slate-500">PnL</th>
                    <th className="px-4 py-3 text-right text-xs uppercase tracking-wider text-slate-500">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((trade, index) => (
                    <tr key={`${trade.entry_time}-${index}`} className="border-b border-white/5">
                      <td className={`px-4 py-3 font-semibold ${trade.direction === 'BUY' ? 'text-teal-400' : 'text-red-400'}`}>{trade.direction}</td>
                      <td className="px-4 py-3 text-slate-300">
                        <div className="font-mono">{trade.entry_price.toLocaleString('vi-VN', { maximumFractionDigits: 1 })}</div>
                        <div className="text-xs text-slate-500">{new Date(trade.entry_time).toLocaleString('vi-VN')}</div>
                      </td>
                      <td className="px-4 py-3 text-slate-300">
                        <div className="font-mono">{trade.exit_price.toLocaleString('vi-VN', { maximumFractionDigits: 1 })}</div>
                        <div className="text-xs text-slate-500">{new Date(trade.exit_time).toLocaleString('vi-VN')}</div>
                      </td>
                      <td className={`px-4 py-3 text-right font-mono ${trade.pnl >= 0 ? 'text-teal-400' : 'text-red-400'}`}>
                        {trade.pnl.toLocaleString('vi-VN', { maximumFractionDigits: 0 })}
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-slate-500">{trade.close_reason.replace('_', ' ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
