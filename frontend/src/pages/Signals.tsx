import { useEffect, useMemo, useState } from 'react'
import { Clock, RefreshCw, Sparkles, TrendingDown, TrendingUp } from 'lucide-react'
import { useWebSocket } from '../hooks/useWebSocket'
import type { SignalRecommendation } from '../components/RecommendationCard'

const API_BASE = 'http://localhost:8000'

interface RecommendationFeedResponse {
  items: SignalRecommendation[]
  latest: SignalRecommendation | null
  count: number
}

interface RecommendationReplayRun {
  id: number
  symbol: string
  provider: string
  start_date: string
  end_date: string
  include_ai: boolean
  status: string
  total_signals: number
  created_at: string
  completed_at: string | null
}

type TimelineRecommendation = SignalRecommendation & {
  position_direction?: string
  entry_price?: number
  exit_price?: number
  pnl_points?: number
}

interface RecommendationHistoryItem {
  id: number
  run_id: number
  signal_id: string
  symbol: string
  recommendation: string
  confidence: number
  generated_at: string
  current_price: number
  ai_applied: boolean
  app_recommendation: TimelineRecommendation
  ai_recommendation: (TimelineRecommendation & { ai_source?: string }) | null
}

interface RecommendationHistoryResponse {
  items: RecommendationHistoryItem[]
  runs: RecommendationReplayRun[]
}


interface TradeBlock {
  run_id: number
  symbol: string
  direction: 'BUY' | 'SELL'
  entry_time: string
  exit_time: string | null
  entry_price: number
  exit_price: number | null
  close_reason: string
  pnl_points: number | null
  confidence: number
}

interface TradeBlockSummary {
  totalTrades: number
  closedTrades: number
  openTrades: number
  wins: number
  losses: number
  totalPnlPoints: number
}

function calculatePnlPoints(direction: 'BUY' | 'SELL', entryPrice: number, marketPrice: number) {
  const signed = direction === 'BUY' ? marketPrice - entryPrice : entryPrice - marketPrice
  return Number(signed.toFixed(1))
}

function scoreBadge(score: number) {
  if (score >= 75) return 'badge-high'
  if (score >= 50) return 'badge-mid'
  return 'badge-low'
}

function statusColor(status: string) {
  if (status === 'BUY') return 'text-teal-400'
  if (status === 'SELL') return 'text-red-400'
  if (status === 'TAKE_PROFIT') return 'text-emerald-300'
  if (status === 'STOP_LOSS' || status === 'ATR_TRAILING_STOP' || status === 'SIGNAL_FLIP') return 'text-rose-300'
  if (status === 'HOLD') return 'text-amber-400'
  return 'text-slate-500'
}

function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A'
  return value.toLocaleString('vi-VN', { maximumFractionDigits: 1 })
}

function formatTime(value: string) {
  try {
    return new Date(value).toLocaleString('vi-VN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return '--'
  }
}

function directionChip(recommendation: string) {
  if (recommendation === 'BUY') {
    return <span className="flex items-center gap-1 text-teal-400"><TrendingUp size={14} />BUY</span>
  }
  if (recommendation === 'SELL') {
    return <span className="flex items-center gap-1 text-red-400"><TrendingDown size={14} />SELL</span>
  }
  if (recommendation === 'TAKE_PROFIT') {
    return <span className="text-emerald-300">TAKE_PROFIT</span>
  }
  if (recommendation === 'STOP_LOSS' || recommendation === 'ATR_TRAILING_STOP' || recommendation === 'SIGNAL_FLIP') {
    return <span className="text-rose-300">{recommendation}</span>
  }
  return <span className="text-slate-500">{recommendation}</span>
}


function buildTradeBlocks(items: RecommendationHistoryItem[]): TradeBlock[] {
  const chronological = [...items].sort((a, b) => new Date(a.generated_at).getTime() - new Date(b.generated_at).getTime())
  const openTradeByRun = new Map<number, TradeBlock>()
  const blocks: TradeBlock[] = []

  for (const item of chronological) {
    if (item.recommendation === 'BUY' || item.recommendation === 'SELL') {
      const payload = item.app_recommendation
      openTradeByRun.set(item.run_id, {
        run_id: item.run_id,
        symbol: item.symbol,
        direction: item.recommendation,
        entry_time: item.generated_at,
        exit_time: null,
        entry_price: payload.entry_price ?? item.current_price,
        exit_price: item.current_price,
        close_reason: 'OPEN',
        pnl_points: calculatePnlPoints(item.recommendation, payload.entry_price ?? item.current_price, item.current_price),
        confidence: item.confidence,
      })
      continue
    }

    const openTrade = openTradeByRun.get(item.run_id)
    if (openTrade) {
      openTrade.exit_price = item.current_price
      openTrade.pnl_points = calculatePnlPoints(openTrade.direction, openTrade.entry_price, item.current_price)
    }

    if (!['TAKE_PROFIT', 'STOP_LOSS', 'ATR_TRAILING_STOP', 'SIGNAL_FLIP'].includes(item.recommendation)) {
      continue
    }

    if (!openTrade) continue

    const payload = item.app_recommendation
    const nextBlock: TradeBlock = {
      ...openTrade,
      exit_time: item.generated_at,
      exit_price: payload.exit_price ?? item.current_price,
      close_reason: item.recommendation,
      pnl_points: typeof payload.pnl_points === 'number' ? payload.pnl_points : null,
    }
    blocks.push(nextBlock)
    openTradeByRun.delete(item.run_id)
  }

  for (const openTrade of openTradeByRun.values()) {
    blocks.push(openTrade)
  }

  return blocks.sort((a, b) => new Date(b.entry_time).getTime() - new Date(a.entry_time).getTime()).slice(0, 40)
}

function summarizeTradeBlocks(blocks: TradeBlock[]): TradeBlockSummary {
  const closedTrades = blocks.filter((trade) => trade.exit_time)
  const openTrades = blocks.filter((trade) => !trade.exit_time)
  const pnlValues = blocks
    .map((trade) => trade.pnl_points)
    .filter((value): value is number => typeof value === 'number')

  return {
    totalTrades: blocks.length,
    closedTrades: closedTrades.length,
    openTrades: openTrades.length,
    wins: pnlValues.filter((value) => value > 0).length,
    losses: pnlValues.filter((value) => value < 0).length,
    totalPnlPoints: Number(pnlValues.reduce((sum, value) => sum + value, 0).toFixed(1)),
  }
}

export default function Signals() {
  const { latestRecommendation, isConnected } = useWebSocket('ws://localhost:8000/ws')
  const [signals, setSignals] = useState<SignalRecommendation[]>([])
  const [history, setHistory] = useState<RecommendationHistoryItem[]>([])
  const [runs, setRuns] = useState<RecommendationReplayRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState<number | 'all'>('all')
  const [hasAutoSelectedRun, setHasAutoSelectedRun] = useState(false)
  const [buySellOnly, setBuySellOnly] = useState(true)
  const [aiOnly, setAiOnly] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isReplaying, setIsReplaying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadAll = async () => {
    const historyUrl =
      selectedRunId === 'all'
        ? `${API_BASE}/v1/market/recommendation-history?limit=200`
        : `${API_BASE}/v1/market/recommendation-history?limit=200&run_id=${selectedRunId}`
    const [feedResponse, historyResponse] = await Promise.all([
      fetch(`${API_BASE}/v1/market/recommendations?limit=20`),
      fetch(historyUrl),
    ])
    if (!feedResponse.ok) {
      throw new Error(`Feed HTTP ${feedResponse.status}`)
    }
    if (!historyResponse.ok) {
      throw new Error(`History HTTP ${historyResponse.status}`)
    }
    const feedData: RecommendationFeedResponse = await feedResponse.json()
    const historyData: RecommendationHistoryResponse = await historyResponse.json()
    setSignals(feedData.items ?? [])
    setHistory(historyData.items ?? [])
    setRuns(historyData.runs ?? [])
    if (!hasAutoSelectedRun && selectedRunId === 'all') {
      const latestCompletedRun = (historyData.runs ?? []).find((run) => run.status === 'completed')
      if (latestCompletedRun) {
        setSelectedRunId(latestCompletedRun.id)
        setHasAutoSelectedRun(true)
      }
    }
  }

  useEffect(() => {
    let isMounted = true
    void (async () => {
      try {
        setError(null)
        await loadAll()
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load signal feed')
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    })()

    const timer = setInterval(() => {
      void loadAll().catch((err) => {
        console.error('Failed to refresh signal data:', err)
      })
    }, runs.some((run) => run.status === 'running') ? 10000 : 30000)

    return () => {
      isMounted = false
      clearInterval(timer)
    }
  }, [hasAutoSelectedRun, selectedRunId, runs])

  useEffect(() => {
    if (!latestRecommendation) return
    setSignals((prev) => {
      const next = [latestRecommendation, ...prev.filter((item) => item.signal_id !== latestRecommendation.signal_id)]
      return next.slice(0, 20)
    })
  }, [latestRecommendation])

  const latestRun = runs[0]
  const filteredHistory = useMemo(() => {
    let items = [...history]
    if (buySellOnly) {
      items = items.filter((item) => ['BUY', 'SELL', 'TAKE_PROFIT', 'STOP_LOSS', 'ATR_TRAILING_STOP', 'SIGNAL_FLIP'].includes(item.recommendation))
    }
    if (aiOnly) {
      items = items.filter((item) => item.ai_applied)
    }
    return items.slice(0, 100)
  }, [aiOnly, buySellOnly, history])

  const tradeBlocks = useMemo(() => buildTradeBlocks(history), [history])
  const tradeBlockSummary = useMemo(() => summarizeTradeBlocks(tradeBlocks), [tradeBlocks])

  const runReplay = async () => {
    try {
      setIsReplaying(true)
      setError(null)
      const today = new Date()
      const endDate = today.toISOString().slice(0, 10)
      const startDate = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
      const response = await fetch(`${API_BASE}/v1/market/recommendation-history/replay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: 'VN30F1M',
          start_date: startDate,
          end_date: endDate,
          include_ai: true,
        }),
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Replay failed')
      }
      if (payload.run_id) {
        setSelectedRunId(payload.run_id)
      }
      await loadAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Replay failed')
    } finally {
      setIsReplaying(false)
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-200">Signal Feed</h1>
          <p className="mt-0.5 text-xs text-slate-500">Realtime feed, historical replay, and side-by-side engine versus AI recommendation narratives.</p>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="inline-flex items-center gap-1.5 rounded border border-white/10 bg-slate-900/60 px-3 py-1.5 text-slate-300">
            {isConnected ? <span className="live-dot" /> : <RefreshCw size={12} className="animate-spin text-amber-400" />}
            {isConnected ? 'WebSocket live' : 'Reconnecting'}
          </span>
          <button type="button" onClick={runReplay} disabled={isReplaying} className="inline-flex items-center gap-1.5 rounded border border-teal-500/20 bg-teal-500/10 px-3 py-1.5 text-teal-300 disabled:opacity-50">
            {isReplaying ? <RefreshCw size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {isReplaying ? 'Replaying 30d...' : 'Replay 30d recommendations'}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-white/5 bg-slate-900/40 px-4 py-3 text-xs text-slate-400">
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={buySellOnly} onChange={(event) => setBuySellOnly(event.target.checked)} className="h-4 w-4 accent-teal-500" />
          Entries + exits only
        </label>
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={aiOnly} onChange={(event) => setAiOnly(event.target.checked)} className="h-4 w-4 accent-amber-400" />
          AI only
        </label>
        <label className="inline-flex items-center gap-2">
          <span>Run</span>
          <select
            value={selectedRunId}
            onChange={(event) => setSelectedRunId(event.target.value === 'all' ? 'all' : Number(event.target.value))}
            className="rounded border border-white/10 bg-slate-950 px-2 py-1 text-slate-300"
          >
            <option value="all">All runs</option>
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                #{run.id} {run.status} {run.start_date} {'->'} {run.end_date}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="glass-card overflow-hidden">
        <div className="border-b border-white/5 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-100">Trade Blocks</h2>
          <p className="text-xs text-slate-500">Collapsed view of each completed trade with entry, exit, P/L, and close reason.</p>
        </div>

        <div className="grid grid-cols-2 gap-3 border-b border-white/5 bg-slate-950/40 px-4 py-3 text-xs md:grid-cols-6">
          <div>
            <div className="text-slate-500">Total</div>
            <div className="mt-1 font-semibold text-slate-200">{tradeBlockSummary.totalTrades}</div>
          </div>
          <div>
            <div className="text-slate-500">Closed</div>
            <div className="mt-1 font-semibold text-slate-200">{tradeBlockSummary.closedTrades}</div>
          </div>
          <div>
            <div className="text-slate-500">Open</div>
            <div className="mt-1 font-semibold text-slate-200">{tradeBlockSummary.openTrades}</div>
          </div>
          <div>
            <div className="text-slate-500">Wins</div>
            <div className="mt-1 font-semibold text-teal-300">{tradeBlockSummary.wins}</div>
          </div>
          <div>
            <div className="text-slate-500">Losses</div>
            <div className="mt-1 font-semibold text-rose-300">{tradeBlockSummary.losses}</div>
          </div>
          <div>
            <div className="text-slate-500">Total P/L</div>
            <div className={`mt-1 font-semibold ${tradeBlockSummary.totalPnlPoints >= 0 ? 'text-teal-300' : 'text-rose-300'}`}>
              {tradeBlockSummary.totalPnlPoints > 0 ? '+' : ''}
              {tradeBlockSummary.totalPnlPoints.toFixed(1)} pts
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5">
                <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">Direction</th>
                <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">Entry Time</th>
                <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">Exit Time</th>
                <th className="px-4 py-3 text-right text-xs uppercase tracking-wider text-slate-500">Entry</th>
                <th className="px-4 py-3 text-right text-xs uppercase tracking-wider text-slate-500">Exit</th>
                <th className="px-4 py-3 text-right text-xs uppercase tracking-wider text-slate-500">P/L</th>
                <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">Reason</th>
              </tr>
            </thead>
            <tbody>
              {tradeBlocks.map((trade) => (
                <tr key={`${trade.run_id}-${trade.entry_time}-${trade.direction}`} className="border-b border-white/5">
                  <td className="px-4 py-3">{directionChip(trade.direction)}</td>
                  <td className="px-4 py-3 text-xs text-slate-300">{formatTime(trade.entry_time)}</td>
                  <td className="px-4 py-3 text-xs text-slate-300">{trade.exit_time ? formatTime(trade.exit_time) : 'OPEN'}</td>
                  <td className="px-4 py-3 text-right font-mono text-slate-300">{formatPrice(trade.entry_price)}</td>
                  <td className="px-4 py-3 text-right font-mono text-slate-300">{formatPrice(trade.exit_price)}</td>
                  <td className={`px-4 py-3 text-right font-mono ${typeof trade.pnl_points === 'number' ? (trade.pnl_points >= 0 ? 'text-teal-400' : 'text-red-400') : 'text-slate-500'}`}>
                    {typeof trade.pnl_points === 'number' ? `${trade.pnl_points > 0 ? '+' : ''}${trade.pnl_points.toFixed(1)} pts` : '--'}
                  </td>
                  <td className={`px-4 py-3 text-xs ${statusColor(trade.close_reason)}`}>{trade.close_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!isLoading && tradeBlocks.length === 0 && (
          <div className="px-6 py-12 text-center text-sm text-slate-500">
            No completed trade blocks yet for the current filters/run.
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.85fr_1.15fr]">
        <div className="glass-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-100">Replay Status</h2>
              <p className="text-xs text-slate-500">Latest historical run for app engine and AI recommendation narrative.</p>
            </div>
            <span className="badge-mid">{runs.length} runs</span>
          </div>

          {latestRun ? (
            <div className="space-y-3 text-sm">
              <div className="rounded-lg border border-white/5 bg-slate-900/40 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-semibold text-slate-200">{latestRun.symbol}</span>
                  <span className={latestRun.status === 'completed' ? 'text-teal-400' : 'text-amber-400'}>{latestRun.status}</span>
                </div>
                <div className="space-y-1 text-xs text-slate-400">
                  <div>Window: {latestRun.start_date} {'->'} {latestRun.end_date}</div>
                  <div>Provider: {latestRun.provider}</div>
                  <div>Signals stored: {latestRun.total_signals}</div>
                  <div>Completed: {latestRun.completed_at ? formatTime(latestRun.completed_at) : '--'}</div>
                </div>
              </div>

              <div className="rounded-lg border border-white/5 bg-slate-900/40 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500">
                  <Clock size={12} />
                  Recent feed
                </div>
                <div className="space-y-2">
                  {signals.slice(0, 5).map((sig) => (
                    <div key={sig.signal_id} className="flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-200">{sig.symbol}</span>
                      <span className={statusColor(sig.recommendation)}>{sig.recommendation}</span>
                      <span className={scoreBadge(sig.confidence)}>{sig.confidence.toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-white/5 bg-slate-900/40 px-4 py-10 text-center text-sm text-slate-500">
              No replay run yet. Use <span className="text-teal-300">Replay 30d recommendations</span> to build old-data history.
            </div>
          )}
        </div>

        <div className="glass-card overflow-hidden">
          <div className="border-b border-white/5 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-100">Historical Recommendation Timeline</h2>
            <p className="text-xs text-slate-500">Each row keeps the raw app recommendation and the AI-enriched version generated from the same historical market snapshot.</p>
          </div>

          {error && (
            <div className="border-b border-red-500/20 bg-red-500/10 px-4 py-3 text-xs text-red-300">
              {error}
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">Time</th>
                  <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">App</th>
                  <th className="px-4 py-3 text-left text-xs uppercase tracking-wider text-slate-500">AI</th>
                  <th className="px-4 py-3 text-right text-xs uppercase tracking-wider text-slate-500">Price</th>
                  <th className="px-4 py-3 text-right text-xs uppercase tracking-wider text-slate-500">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {filteredHistory.map((item) => (
                  <tr key={item.id} className="border-b border-white/5 align-top">
                    <td className="px-4 py-3 text-xs text-slate-400">
                      <div>{formatTime(item.generated_at)}</div>
                      <div className="mt-1 text-[11px] text-slate-600">Run #{item.run_id}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="mb-1 flex items-center gap-2">
                        {directionChip(item.app_recommendation.recommendation)}
                        <span className={scoreBadge(item.app_recommendation.confidence)}>{item.app_recommendation.confidence.toFixed(0)}%</span>
                      </div>
                      <div className="text-xs text-slate-400">
                        {item.app_recommendation.reasoning?.[0] || 'No engine note'}
                      </div>
                      {item.app_recommendation.position_direction && (
                        <div className="mt-1 text-[11px] text-slate-500">
                          {item.app_recommendation.position_direction} | entry {formatPrice(item.app_recommendation.entry_price)}
                          {item.app_recommendation.exit_price ? ` -> exit ${formatPrice(item.app_recommendation.exit_price)}` : ''}
                          {typeof item.app_recommendation.pnl_points === 'number' ? ` | P/L ${item.app_recommendation.pnl_points > 0 ? '+' : ''}${item.app_recommendation.pnl_points.toFixed(1)} pts` : ''}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {item.ai_recommendation ? (
                        <>
                          <div className="mb-1 flex items-center gap-2">
                            <span className="inline-flex items-center gap-1 text-amber-300">
                              <Sparkles size={12} />
                              AI note
                            </span>
                            <span className="text-[11px] text-slate-500">{item.ai_recommendation.ai_source || 'LLM'}</span>
                          </div>
                          <div className="text-xs text-slate-300">
                            {item.ai_recommendation.reasoning?.[0] || item.ai_recommendation.risk_note || 'No AI note'}
                          </div>
                        </>
                      ) : (
                        <span className="text-xs text-slate-600">AI not applied</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-300">{formatPrice(item.current_price)}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={scoreBadge(item.confidence)}>{item.confidence.toFixed(0)}%</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!isLoading && filteredHistory.length === 0 && (
            <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
              <Clock size={24} className="text-slate-600" />
              <p className="text-sm text-slate-400">No historical recommendations match the current filters.</p>
              <p className="text-xs text-slate-600">Try another run, turn off filters, or start a new background replay.</p>
            </div>
          )}

          {isLoading && (
            <div className="flex items-center justify-center gap-2 px-6 py-16 text-sm text-slate-500">
              <RefreshCw size={16} className="animate-spin" />
              Loading signal history...
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-4 text-xs text-slate-500">
        <span><span className="badge-high mr-1">75%+</span> Execute bias</span>
        <span><span className="badge-mid mr-1">50-74%</span> Monitor closely</span>
        <span><span className="badge-low mr-1">&lt; 50%</span> Low conviction</span>
        <span className="inline-flex items-center gap-1"><Sparkles size={12} className="text-amber-300" /> AI row keeps the narrative generated from the same historical signal</span>
        <span>Use one replay run at a time for clean position history.</span>
      </div>
    </div>
  )
}
