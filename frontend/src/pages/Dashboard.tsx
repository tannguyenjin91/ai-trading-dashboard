import { useEffect, useMemo, useRef, useState, type ElementType } from 'react'
import {
  AlertCircle,
  BarChart3,
  Briefcase,
  Clock,
  Database,
  Lock,
  RefreshCw,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
  WifiOff,
  Zap,
} from 'lucide-react'

import KillSwitch from '../components/KillSwitch'
import MarketInsightCard from '../components/MarketInsightCard'
import PositionCard from '../components/PositionCard'
import RecommendationCard from '../components/RecommendationCard'
import { useMarketStore, type ConnectionStatus as FeedConnectionStatus } from '../hooks/useMarketStore'
import { useWebSocket } from '../hooks/useWebSocket'

const API_BASE = 'http://localhost:8000'

interface PortfolioItem {
  id: number
  symbol: string
  direction: 'BUY' | 'SELL'
  status: 'OPEN' | 'CLOSED'
  entry_price: number
  current_price: number
  exit_price?: number | null
  take_profit: number | null
  stop_loss: number | null
  opened_at: string
  closed_at: string | null
  close_reason: string | null
  realized_pnl: number
  unrealized_pnl: number
}

interface PortfolioResponse {
  balance: number
  closed_count: number
  equity: number
  history: PortfolioItem[]
  open_count: number
  open_positions: PortfolioItem[]
  realized_pnl: number
  starting_capital: number
  symbol: string
  unrealized_pnl: number
  win_rate: number
  window_days: number
}

interface HistoryEvent {
  id: number
  order_id: number
  symbol: string
  event_type: 'OPEN' | 'ADJUST' | 'CLOSE' | 'MARK_TO_MARKET'
  event_time: string
  status: 'OPEN' | 'CLOSED'
  price: number | null
  pnl: number
  details: Record<string, unknown>
}

interface OrderHistoryResponse {
  window_days: number
  orders: PortfolioItem[]
  events: HistoryEvent[]
}

interface CoverageItem {
  symbol: string
  timeframe: '1m' | '5m' | '15m' | '1D'
  rows: number
  first_timestamp: string | null
  last_timestamp: string | null
}

interface CoverageResponse {
  symbol: string
  history_window_days: number
  last_sync: {
    synced_at?: string
    error?: string
    fetched_rows?: number
    daily_fetched_rows?: number
  }
  items: CoverageItem[]
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

interface RecommendationHistoryItem {
  id: number
  run_id: number
  recommendation: string
  generated_at: string
  current_price: number
  ai_applied: boolean
  app_recommendation: {
    confidence: number
    reasoning?: string[]
  }
  ai_recommendation: {
    reasoning?: string[]
    risk_note?: string
    ai_source?: string
  } | null
}

interface RecommendationHistoryResponse {
  items: RecommendationHistoryItem[]
  runs: RecommendationReplayRun[]
}

function PriceDisplay({ price, prevPrice, isClosed }: { price: number; prevPrice: number; isClosed: boolean }) {
  const [flash, setFlash] = useState<'up' | 'down' | null>(null)
  const prevRef = useRef(prevPrice)

  useEffect(() => {
    if (isClosed || price === 0 || prevRef.current === 0) {
      prevRef.current = price
      return
    }
    if (price > prevRef.current) setFlash('up')
    if (price < prevRef.current) setFlash('down')
    prevRef.current = price
    const timer = setTimeout(() => setFlash(null), 600)
    return () => clearTimeout(timer)
  }, [isClosed, price])

  const flashClass = flash === 'up' ? 'price-flash-up' : flash === 'down' ? 'price-flash-down' : ''
  return (
    <span className={`text-2xl font-mono tracking-tight text-white transition-colors duration-300 ${flashClass}`}>
      {price > 0 ? price.toLocaleString('en-US', { minimumFractionDigits: 1 }) : '---'}
    </span>
  )
}

function FeedStatusBadge({
  status,
  source,
  isStale,
  marketSession,
}: {
  status: FeedConnectionStatus
  source: string
  isStale: boolean
  marketSession: string
}) {
  if (marketSession === 'CLOSED') {
    return (
      <div className="flex items-center gap-1.5 opacity-80">
        <Lock size={12} className="text-slate-500" />
        <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Market Closed</span>
      </div>
    )
  }
  if (isStale) {
    return (
      <div className="flex items-center gap-1.5">
        <Clock size={12} className="text-amber-400" />
        <span className="text-xs font-bold uppercase tracking-wider text-amber-400">Stale</span>
      </div>
    )
  }
  if (source === 'dnse_websocket') {
    return (
      <div className="flex items-center gap-1.5">
        <span className="live-dot" />
        <span className="text-xs font-bold uppercase tracking-wider text-teal-400">Live WS</span>
      </div>
    )
  }
  if (source === 'dnse_rest') {
    return (
      <div className="flex items-center gap-1.5">
        <span className="inline-block h-2 w-2 rounded-full bg-blue-400" style={{ animation: 'livePulse 2s ease-in-out infinite' }} />
        <span className="text-xs font-bold uppercase tracking-wider text-blue-400">REST Poll</span>
      </div>
    )
  }
  if (status === 'reconnecting' || status === 'connecting') {
    return (
      <div className="flex items-center gap-1.5">
        <RefreshCw size={12} className="animate-spin text-amber-400" />
        <span className="text-xs font-bold uppercase tracking-wider text-amber-400">Reconnecting</span>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-1.5">
      <WifiOff size={12} className="text-red-400" />
      <span className="text-xs font-bold uppercase tracking-wider text-red-400">Offline</span>
    </div>
  )
}

function SummaryCard({
  label,
  value,
  subtext,
  icon: Icon,
  tone = 'text-slate-100',
}: {
  label: string
  value: string
  subtext: string
  icon: ElementType
  tone?: string
}) {
  return (
    <div className="glass-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</span>
        <Icon size={14} className="text-slate-500" />
      </div>
      <p className={`text-2xl font-bold tracking-tight ${tone}`}>{value}</p>
      <p className="mt-1 text-xs text-slate-500">{subtext}</p>
    </div>
  )
}

function formatClock(value?: string | null) {
  if (!value) return '--:--:--'
  try {
    return new Date(value).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return '--:--:--'
  }
}

function formatStamp(value?: string | null) {
  if (!value) return '--'
  try {
    return new Date(value).toLocaleString('vi-VN')
  } catch {
    return '--'
  }
}

function formatMoney(value: number) {
  return value.toLocaleString('vi-VN', { maximumFractionDigits: 0 })
}

function eventTone(eventType: HistoryEvent['event_type']) {
  if (eventType === 'OPEN') return 'text-teal-400'
  if (eventType === 'CLOSE') return 'text-red-400'
  if (eventType === 'ADJUST') return 'text-amber-400'
  return 'text-slate-400'
}

export default function Dashboard() {
  const { latestTick, latestInsight, latestRecommendation } = useWebSocket('ws://localhost:8000/ws')

  const tick = useMarketStore((state) => state.ticks['VN30F1M'])
  const connectionStatus = useMarketStore((state) => state.connectionStatus)
  const feedSource = useMarketStore((state) => state.feedSource)
  const isStale = useMarketStore((state) => state.isStale)
  const marketSession = useMarketStore((state) => state.marketSession)
  const lastTickAt = useMarketStore((state) => state.lastTickAt)

  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null)
  const [history, setHistory] = useState<OrderHistoryResponse | null>(null)
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null)
  const [recommendationHistory, setRecommendationHistory] = useState<RecommendationHistoryResponse | null>(null)

  useEffect(() => {
    let active = true
    const loadDashboard = async () => {
      try {
        const [portfolioRes, historyRes, coverageRes, recommendationHistoryRes] = await Promise.all([
          fetch(`${API_BASE}/v1/market/portfolio?limit=12&days=30`),
          fetch(`${API_BASE}/v1/market/order-history?limit=40&days=30`),
          fetch(`${API_BASE}/v1/market/data-coverage`),
          fetch(`${API_BASE}/v1/market/recommendation-history?limit=30`),
        ])
        if (!portfolioRes.ok || !historyRes.ok || !coverageRes.ok || !recommendationHistoryRes.ok) return
        const portfolioData: PortfolioResponse = await portfolioRes.json()
        const historyData: OrderHistoryResponse = await historyRes.json()
        const coverageData: CoverageResponse = await coverageRes.json()
        const recommendationHistoryData: RecommendationHistoryResponse = await recommendationHistoryRes.json()
        if (!active) return
        setPortfolio(portfolioData)
        setHistory(historyData)
        setCoverage(coverageData)
        setRecommendationHistory(recommendationHistoryData)
      } catch (error) {
        console.error('Failed to load dashboard:', error)
      }
    }

    loadDashboard()
    const timer = setInterval(loadDashboard, 30000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (!latestRecommendation) return
    void (async () => {
      try {
        const [portfolioRes, historyRes, coverageRes, recommendationHistoryRes] = await Promise.all([
          fetch(`${API_BASE}/v1/market/portfolio?limit=12&days=30`),
          fetch(`${API_BASE}/v1/market/order-history?limit=40&days=30`),
          fetch(`${API_BASE}/v1/market/data-coverage`),
          fetch(`${API_BASE}/v1/market/recommendation-history?limit=30`),
        ])
        if (!portfolioRes.ok || !historyRes.ok || !coverageRes.ok || !recommendationHistoryRes.ok) return
        setPortfolio(await portfolioRes.json())
        setHistory(await historyRes.json())
        setCoverage(await coverageRes.json())
        setRecommendationHistory(await recommendationHistoryRes.json())
      } catch (error) {
        console.error('Failed to refresh dashboard state:', error)
      }
    })()
  }, [latestRecommendation])

  const price = tick?.price ?? latestTick?.price ?? 0
  const prevPrice = tick?.prevPrice ?? price
  const changePct = tick?.changePct ?? latestTick?.changePct ?? 0
  const positions = portfolio?.open_positions ?? []
  const orderEvents = useMemo(() => (history?.events ?? []).filter((event) => event.event_type !== 'MARK_TO_MARKET').slice(0, 20), [history])
  const coverageItems = useMemo(() => coverage?.items ?? [], [coverage])
  const replayRun = recommendationHistory?.runs?.[0] ?? null
  const replaySignals = useMemo(
    () => (recommendationHistory?.items ?? []).filter((item) => ['BUY', 'SELL'].includes(item.recommendation)).slice(0, 5),
    [recommendationHistory],
  )

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div className="glass-card flex flex-col gap-4 border-l-4 border-l-teal-500 p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-6">
          <FeedStatusBadge status={connectionStatus} source={feedSource} isStale={isStale} marketSession={marketSession} />
          <div className="hidden h-4 w-px bg-white/10 lg:block" />
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-bold text-slate-100">{portfolio?.symbol || 'VN30F1M'}</span>
            <PriceDisplay price={price} prevPrice={prevPrice} isClosed={marketSession === 'CLOSED'} />
            {changePct !== 0 && (
              <span className={`flex items-center gap-0.5 text-sm font-bold font-mono ${changePct >= 0 ? 'text-teal-400' : 'text-red-400'}`}>
                {changePct >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {changePct > 0 ? '+' : ''}
                {changePct.toFixed(2)}%
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-medium">
          <div className="flex items-center gap-1.5 text-slate-400">
            <Clock size={12} />
            <span className="text-slate-200">{formatClock(lastTickAt)}</span>
          </div>
          <div className="rounded border border-teal-500/20 bg-teal-500/10 px-3 py-1 text-teal-300">SIGNAL ONLY</div>
        </div>
      </div>

      {marketSession === 'CLOSED' ? (
        <div className="flex items-start gap-2 rounded-lg border border-slate-700/50 bg-slate-800/50 p-3 text-xs text-slate-400">
          <Lock size={14} className="mt-0.5 shrink-0" />
          <p>The market is closed. Signals use the latest confirmed session data and resume automatically next session.</p>
        </div>
      ) : (isStale || connectionStatus === 'disconnected') && price > 0 ? (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-400">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <p>{connectionStatus === 'disconnected' ? 'Market feed is disconnected. Dashboard shows the last known price.' : 'Feed looks stale. Signal journaling uses the latest confirmed price until freshness returns.'}</p>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            <SummaryCard
              label="Starting Capital"
              value={portfolio ? formatMoney(portfolio.starting_capital) : '---'}
              subtext="Signal journal base"
              icon={Wallet}
            />
            <SummaryCard
              label="Equity"
              value={portfolio ? formatMoney(portfolio.equity) : '---'}
              subtext={`${portfolio?.open_count ?? 0} open positions`}
              icon={BarChart3}
            />
            <SummaryCard
              label="Realized PnL"
              value={portfolio ? formatMoney(portfolio.realized_pnl) : '---'}
              subtext={`${portfolio?.closed_count ?? 0} closed trades`}
              icon={Briefcase}
              tone={(portfolio?.realized_pnl ?? 0) >= 0 ? 'text-teal-400' : 'text-red-400'}
            />
            <SummaryCard
              label="Win Rate"
              value={portfolio ? `${portfolio.win_rate.toFixed(1)}%` : '---'}
              subtext={`${portfolio?.window_days ?? 30}-day view`}
              icon={Target}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <h2 className="mb-2 ml-1 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-teal-400">
                <Zap size={12} className="text-amber-400" /> Market Insight
              </h2>
              <MarketInsightCard insight={latestInsight} />
            </div>

            <div className="space-y-4">
              <div>
                <h2 className="mb-2 ml-1 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                  <Target size={12} /> Latest Recommendation
                </h2>
                <RecommendationCard signal={latestRecommendation} />
              </div>
              <div className="glass-card border border-amber-500/10 bg-amber-500/5 p-4">
                <KillSwitch />
              </div>
            </div>
          </div>

          <div className="glass-card p-4">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                  <Database size={15} className="text-blue-400" />
                  Data Coverage
                </h2>
                <p className="text-xs text-slate-500">Local vnstock cache used for recommendation fallback and 30-day replay.</p>
              </div>
              <div className="text-right text-xs text-slate-500">
                <div>{coverage?.history_window_days ?? 30}-day target</div>
                <div>{coverage?.last_sync?.synced_at ? `Last sync ${formatStamp(coverage.last_sync.synced_at)}` : 'Awaiting background sync'}</div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {coverageItems.map((item) => (
                <div key={item.timeframe} className="rounded-lg border border-white/5 bg-slate-900/40 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{item.timeframe}</span>
                    <span className="text-[10px] text-slate-400">{item.symbol}</span>
                  </div>
                  <div className="text-xl font-bold text-slate-100">{formatMoney(item.rows)}</div>
                  <div className="mt-1 text-[11px] text-slate-500">bars in local cache</div>
                  <div className="mt-3 space-y-1 text-[11px] text-slate-400">
                    <div>From: {formatStamp(item.first_timestamp)}</div>
                    <div>To: {formatStamp(item.last_timestamp)}</div>
                  </div>
                </div>
              ))}
            </div>

            {coverage?.last_sync?.error ? (
              <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                Last history sync error: {coverage.last_sync.error}
              </div>
            ) : (
              <div className="mt-4 flex flex-wrap gap-4 text-xs text-slate-500">
                <span>Latest 1m sync: {coverage?.last_sync?.fetched_rows ?? 0} rows</span>
                <span>Latest 1D sync: {coverage?.last_sync?.daily_fetched_rows ?? 0} rows</span>
              </div>
            )}
          </div>

          <div className="glass-card p-4">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-100">Open Recommendation Orders</h2>
                <p className="text-xs text-slate-500">Active simulated orders generated from recommendation signals.</p>
              </div>
              <span className="rounded border border-white/10 bg-slate-900/60 px-3 py-1 text-xs text-slate-300">{positions.length} active</span>
            </div>

            {positions.length > 0 ? (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {positions.map((position) => (
                  <PositionCard
                    key={position.id}
                    position={{
                      id: String(position.id),
                      symbol: position.symbol,
                      direction: position.direction === 'BUY' ? 'LONG' : 'SHORT',
                      entry: position.entry_price,
                      current: position.current_price,
                      pnl: position.entry_price > 0 ? (position.unrealized_pnl / position.entry_price) * 100 : 0,
                      sl: position.stop_loss ?? position.entry_price,
                      tp: position.take_profit ?? position.current_price,
                    }}
                  />
                ))}
              </div>
            ) : (
              <div className="flex min-h-[180px] flex-col items-center justify-center opacity-40">
                <Briefcase size={32} className="mb-2 text-slate-500" />
                <p className="text-sm font-medium text-slate-400">No open recommendation orders</p>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="glass-card overflow-hidden">
            <div className="flex items-start justify-between border-b border-white/5 px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-100">Historical Recommendation Replay</h2>
                <p className="text-xs text-slate-500">Recommendation history generated from old candles, with app output and AI commentary.</p>
              </div>
              <div className="text-right text-xs text-slate-500">
                <div>{replayRun ? `Run #${replayRun.id}` : 'No run yet'}</div>
                <div className={replayRun?.status === 'completed' ? 'text-teal-400' : replayRun?.status === 'running' ? 'text-amber-400' : 'text-slate-500'}>
                  {replayRun?.status || '--'}
                </div>
              </div>
            </div>

            {replaySignals.length > 0 ? (
              <div className="divide-y divide-white/5">
                {replaySignals.map((item) => (
                  <div key={item.id} className="px-4 py-3">
                    <div className="mb-1 flex items-center gap-2">
                      <span className={item.recommendation === 'BUY' ? 'text-teal-400' : 'text-red-400'}>{item.recommendation}</span>
                      <span className="text-xs text-slate-200">{formatStamp(item.generated_at)}</span>
                      <span className="ml-auto text-xs text-slate-400">{formatMoney(item.current_price)}</span>
                    </div>
                    <div className="text-xs text-slate-400">
                      {item.app_recommendation.reasoning?.[0] || 'No app reasoning'}
                    </div>
                    <div className="mt-1 text-xs text-amber-200/80">
                      {item.ai_recommendation?.reasoning?.[0] || item.ai_recommendation?.risk_note || 'AI note pending or not applied'}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="px-4 py-8 text-sm text-slate-500">
                Dashboard replay history only shows BUY/SELL by default. Run a 30-day replay or wait for the current run to finish to surface actionable entries here.
              </div>
            )}
          </div>

          <div className="glass-card overflow-hidden">
            <div className="border-b border-white/5 px-4 py-3">
              <h2 className="text-sm font-semibold text-slate-100">Recommendation Order Timeline</h2>
              <p className="text-xs text-slate-500">Open, adjust, and close events over the last 30 days.</p>
            </div>
            <div className="max-h-[420px] overflow-auto">
              {orderEvents.length > 0 ? (
                <div className="divide-y divide-white/5">
                  {orderEvents.map((event) => (
                    <div key={event.id} className="px-4 py-3">
                      <div className="mb-1 flex items-center gap-2">
                        <span className={`text-xs font-bold uppercase tracking-wider ${eventTone(event.event_type)}`}>{event.event_type}</span>
                        <span className="text-xs font-semibold text-slate-200">{event.symbol}</span>
                        <span className="ml-auto text-[10px] text-slate-500">{formatStamp(event.event_time)}</span>
                      </div>
                      <div className="flex items-center justify-between text-xs text-slate-400">
                        <span>Order #{event.order_id}</span>
                        <span>{event.price ? event.price.toLocaleString('vi-VN', { maximumFractionDigits: 1 }) : '---'}</span>
                      </div>
                      <div className="mt-1 flex items-center justify-between text-xs">
                        <span className="text-slate-500">{String(event.details.close_reason || event.details.direction || 'signal update')}</span>
                        <span className={event.pnl >= 0 ? 'text-teal-400' : 'text-red-400'}>
                          {event.pnl === 0 ? '0' : formatMoney(event.pnl)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="px-6 py-12 text-center text-sm text-slate-500">No order events recorded in the last 30 days.</div>
              )}
            </div>
          </div>

          <div className="glass-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-100">Closed Order Results</h2>
                <p className="text-xs text-slate-500">Most recent recommendation trades and their outcomes.</p>
              </div>
              <span className="text-xs text-slate-500">{history?.orders.length ?? 0} rows</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/5">
                    <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-slate-500">Symbol</th>
                    <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-slate-500">Lifecycle</th>
                    <th className="px-4 py-3 text-right text-[11px] font-medium uppercase tracking-wider text-slate-500">Open</th>
                    <th className="px-4 py-3 text-right text-[11px] font-medium uppercase tracking-wider text-slate-500">Close</th>
                    <th className="px-4 py-3 text-right text-[11px] font-medium uppercase tracking-wider text-slate-500">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {(history?.orders ?? []).map((item) => (
                    <tr key={item.id} className="border-b border-white/5">
                      <td className="px-4 py-3 font-semibold text-slate-200">{item.symbol}</td>
                      <td className="px-4 py-3 text-xs text-slate-400">
                        <div className={item.direction === 'BUY' ? 'text-teal-400' : 'text-red-400'}>{item.direction}</div>
                        <div>{item.close_reason || item.status}</div>
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-slate-300">
                        <div className="font-mono">{item.entry_price.toLocaleString('vi-VN', { maximumFractionDigits: 1 })}</div>
                        <div className="text-slate-500">{formatStamp(item.opened_at)}</div>
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-slate-300">
                        <div className="font-mono">{item.exit_price?.toLocaleString('vi-VN', { maximumFractionDigits: 1 }) ?? '---'}</div>
                        <div className="text-slate-500">{formatStamp(item.closed_at)}</div>
                      </td>
                      <td className={`px-4 py-3 text-right font-mono ${item.status === 'OPEN' ? 'text-amber-400' : item.realized_pnl >= 0 ? 'text-teal-400' : 'text-red-400'}`}>
                        {item.status === 'OPEN' ? formatMoney(item.unrealized_pnl) : formatMoney(item.realized_pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
