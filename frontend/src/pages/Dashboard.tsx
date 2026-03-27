// frontend/src/pages/Dashboard.tsx
import { useState, useEffect, useRef } from 'react'
import { Activity, AlertCircle, Briefcase, Zap, Target, WifiOff, RefreshCw, Clock, TrendingUp, TrendingDown, Lock } from 'lucide-react'
import { useWebSocket } from '../hooks/useWebSocket'
import { useMarketStore, type ConnectionStatus as FeedConnectionStatus } from '../hooks/useMarketStore'
import KillSwitch from '../components/KillSwitch'
import AgentLog from '../components/AgentLog'
import RecommendationCard from '../components/RecommendationCard'
import MarketInsightCard from '../components/MarketInsightCard'

// ── Price Flash Component ─────────────────────────────────────────────────────
function PriceDisplay({ price, prevPrice, isClosed }: { price: number, prevPrice: number, isClosed: boolean }) {
  const [flash, setFlash] = useState<'up' | 'down' | null>(null)
  const prevRef = useRef(prevPrice)

  useEffect(() => {
    if (isClosed || price === 0 || prevRef.current === 0) {
      prevRef.current = price
      return
    }
    if (price > prevRef.current) {
      setFlash('up')
    } else if (price < prevRef.current) {
      setFlash('down')
    }
    prevRef.current = price
    const timer = setTimeout(() => setFlash(null), 600)
    return () => clearTimeout(timer)
  }, [price])

  const flashClass = flash === 'up' ? 'price-flash-up' : flash === 'down' ? 'price-flash-down' : ''

  return (
    <span className={`text-2xl font-mono tracking-tight text-white transition-colors duration-300 ${flashClass}`}>
      {price > 0 ? price.toLocaleString('en-US', { minimumFractionDigits: 1 }) : '---'}
    </span>
  )
}

function FeedStatusBadge({ status, source, isStale, marketSession }: { status: FeedConnectionStatus, source: string, isStale: boolean, marketSession: string }) {
  if (marketSession === 'CLOSED') {
    return (
      <div className="flex items-center gap-1.5 opacity-80">
        <Lock size={12} className="text-slate-500" />
        <span className="text-slate-400 text-xs font-bold uppercase tracking-wider">Market Closed</span>
      </div>
    )
  }

  if (isStale) {
    return (
      <div className="flex items-center gap-1.5">
        <Clock size={12} className="text-amber-400" />
        <span className="text-amber-400 text-xs font-bold uppercase tracking-wider">Stale</span>
      </div>
    )
  }

  if (source === 'dnse_websocket') {
    return (
      <div className="flex items-center gap-1.5">
        <span className="live-dot" />
        <span className="text-teal-400 text-xs font-bold uppercase tracking-wider">Live</span>
        <span className="text-[9px] text-slate-500 ml-1">WS</span>
      </div>
    )
  }

  if (source === 'dnse_rest') {
    return (
      <div className="flex items-center gap-1.5">
        <span className="inline-block w-2 h-2 rounded-full bg-blue-400" style={{ animation: 'livePulse 2s ease-in-out infinite' }} />
        <span className="text-blue-400 text-xs font-bold uppercase tracking-wider">Live</span>
        <span className="text-[9px] text-slate-500 ml-1">REST</span>
      </div>
    )
  }

  if (source === 'mock') {
    return (
      <div className="flex items-center gap-1.5">
        <span className="inline-block w-2 h-2 rounded-full bg-amber-400" style={{ animation: 'livePulse 2s ease-in-out infinite' }} />
        <span className="text-amber-400 text-xs font-bold uppercase tracking-wider">Live</span>
        <span className="text-[9px] text-slate-500 ml-1">MOCK</span>
      </div>
    )
  }

  if (status === 'reconnecting' || status === 'connecting') {
    return (
      <div className="flex items-center gap-1.5">
        <RefreshCw size={12} className="text-amber-400 animate-spin" />
        <span className="text-amber-400 text-xs font-bold uppercase tracking-wider">Reconnecting</span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5">
      <WifiOff size={12} className="text-red-400" />
      <span className="text-red-400 text-xs font-bold uppercase tracking-wider">Offline</span>
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const { isConnected, latestStatus, latestTick, latestInsight, latestRecommendation, messages } = useWebSocket('ws://localhost:8000/ws')
  
  // Zustand market store — realtime data from WebSocket
  const tick = useMarketStore((s) => s.ticks['VN30F1M'])
  const connectionStatus = useMarketStore((s) => s.connectionStatus)
  const feedSource = useMarketStore((s) => s.feedSource)
  const isStale = useMarketStore((s) => s.isStale)
  const marketSession = useMarketStore((s) => s.marketSession)
  const lastTickAt = useMarketStore((s) => s.lastTickAt)
  
  const [positions, setPositions] = useState<any[]>([])
  const [logs, setLogs] = useState<any[]>([])

  useEffect(() => {
    const latestMsg = messages[0]
    if (!latestMsg) return

    if (latestMsg.type === 'DECISION') {
      const decision = latestMsg.data
      setLogs(prev => [{
        id: Date.now().toString(),
        time: new Date().toLocaleTimeString(),
        action: decision.action || 'EXECUTE',
        score: decision.confidence || 0,
        symbol: decision.symbol || 'VN30F1M',
        note: decision.rationale || 'AI executed decision'
      }, ...prev].slice(0, 10))
    } else if (latestMsg.type === 'POSITION') {
      setPositions(prev => {
        const exist = prev.find(p => p.order_id === latestMsg.data.order_id)
        if (exist) return prev.map(p => p.order_id === latestMsg.data.order_id ? latestMsg.data : p)
        return [latestMsg.data, ...prev]
      })
    } else if (latestMsg.type === 'POSITION_CLOSED') {
      const closedId = latestMsg.data.order_id
      setPositions(prev => prev.filter(p => p.order_id !== closedId))
    }
  }, [messages])

  // Derived data from Zustand store
  const price = tick?.price ?? 0
  const prevPrice = tick?.prevPrice ?? price
  const changePct = tick?.changePct ?? 0
  const high = tick?.high ?? 0
  const low = tick?.low ?? 0
  const volume = tick?.sessionVolume ?? tick?.volume ?? 0

  const baseBalance = 50000.00
  const openPnL = positions.reduce((acc, p) => {
    const currentPrice = price || latestTick?.price || p.filled_price
    const diff = p.direction === 'BUY' ? currentPrice - p.filled_price : p.filled_price - currentPrice
    return acc + (diff * 1000)
  }, 0)
  
  const equity = baseBalance + openPnL
  const marginUsed = positions.length * 250
  const freeMargin = equity - marginUsed
  const marginLevel = marginUsed > 0 ? (equity / marginUsed) * 100 : 0

  const formatLastUpdate = (ts?: string | null) => {
    if (!ts) return '--:--:--'
    try {
      return new Date(ts).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch { return '--:--:--' }
  }

  const pnlColorClass = openPnL > 0 ? 'text-teal-400' : openPnL < 0 ? 'text-red-400' : 'text-slate-300'

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      
      {/* 1. TOP SUMMARY / MARKET BAR */}
      <div className="glass-card flex flex-col lg:flex-row lg:items-center justify-between p-4 gap-4 border-l-4 border-l-teal-500">
        
        {/* System & Market Status */}
        <div className="flex flex-wrap items-center gap-6">
          {/* Feed Status */}
          <FeedStatusBadge status={connectionStatus} source={feedSource} isStale={isStale} marketSession={marketSession} />
          
          <div className="h-4 w-px bg-white/10 hidden lg:block"></div>
          
          {/* Core Symbol Quote */}
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-bold text-slate-100">VN30F1M</span>
            <PriceDisplay price={price} prevPrice={prevPrice} isClosed={marketSession === 'CLOSED'} />
            {changePct !== 0 && (
              <span className={`text-sm font-bold font-mono flex items-center gap-0.5 ${changePct >= 0 ? 'text-teal-400' : 'text-red-400'}`}>
                {changePct >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {changePct > 0 ? '+' : ''}{changePct.toFixed(2)}%
              </span>
            )}
          </div>

          <div className="h-4 w-px bg-white/10 hidden lg:block"></div>

          {/* Session High / Low / Volume */}
          <div className="flex items-center gap-4 text-xs text-slate-400">
            {high > 0 && (
              <>
                <div>
                  <span className="text-[10px] text-slate-500 uppercase tracking-widest mr-1">H</span>
                  <span className="text-slate-200 font-mono">{high.toLocaleString('en-US', { minimumFractionDigits: 1 })}</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 uppercase tracking-widest mr-1">L</span>
                  <span className="text-slate-200 font-mono">{low.toLocaleString('en-US', { minimumFractionDigits: 1 })}</span>
                </div>
              </>
            )}
            {volume > 0 && (
              <div>
                <span className="text-[10px] text-slate-500 uppercase tracking-widest mr-1">Vol</span>
                <span className="text-slate-200 font-mono">{(volume / 1000).toFixed(1)}K</span>
              </div>
            )}
          </div>
        </div>

        {/* Info & Mode */}
        <div className="flex items-center gap-4 text-xs font-medium">
          <div className="text-slate-400 flex items-center gap-1.5">
            <Clock size={12} />
            <span className="text-slate-200">{formatLastUpdate(lastTickAt)}</span>
          </div>
          <div className={`px-3 py-1 rounded border ${latestStatus?.is_live_trading_enabled ? 'bg-amber-500/10 border-amber-500/30 text-amber-500' : 'bg-slate-800/50 border-slate-700 text-slate-400'}`}>
            {latestStatus?.is_live_trading_enabled ? 'LIVE TRADING' : 'PAPER TRADING'}
          </div>
        </div>
      </div>

      {/* Stale / Disconnected / Closed Warning Banner */}
      {marketSession === 'CLOSED' ? (
        <div className="flex items-start gap-2 text-xs text-slate-400 bg-slate-800/50 border border-slate-700/50 p-3 rounded-lg animate-fade-in">
          <Lock size={14} className="mt-0.5 shrink-0" />
          <p>The market is currently closed. Auto-trading and AI evaluation evaluate based on the last closing price.</p>
        </div>
      ) : (isStale || connectionStatus === 'disconnected') && price > 0 && (
        <div className="flex items-start gap-2 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 p-3 rounded-lg animate-fade-in">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <p>
            {connectionStatus === 'disconnected'
              ? 'Market data feed is disconnected. Dashboard shows last known prices. Reconnecting...'
              : 'Market data may be stale. AI execution is paused until fresh data is restored.'}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        
        {/* 2. SIDE INFO / ACCOUNT / AI (Left Panel - 4 Cols) */}
        <div className="md:col-span-4 xl:col-span-3 space-y-6">
          
          {/* Performance Overview Card */}
          <div className="glass-card p-5 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-4 opacity-5">
              <Activity size={80} />
            </div>
            <h2 className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-3 flex items-center gap-1.5">
              <Briefcase size={12} /> Live P&L
            </h2>
            <div className={`text-4xl font-black tracking-tighter mb-4 ${pnlColorClass}`}>
              {openPnL > 0 ? '+' : ''}{openPnL.toLocaleString('en-US', {minimumFractionDigits: 2})} <span className="text-lg opacity-50">đ</span>
            </div>
            
            <div className="grid grid-cols-2 gap-4 border-t border-white/5 pt-4">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Balance</p>
                <p className="text-sm font-bold text-slate-200">{baseBalance.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Equity</p>
                <p className={`text-sm font-bold ${equity > baseBalance ? 'text-teal-400' : 'text-slate-200'}`}>{equity.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Free Margin</p>
                <p className="text-sm font-bold text-slate-200">{freeMargin.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Margin Lvl</p>
                <p className="text-sm font-bold text-teal-400">{marginLevel > 0 ? marginLevel.toFixed(1) + '%' : '---'}</p>
              </div>
            </div>
          </div>

          {/* AI Market Insight — Rich Card */}
          <div>
            <h2 className="text-[10px] uppercase tracking-widest text-teal-400 font-bold mb-2 flex items-center gap-1.5">
              <Zap size={12} className="text-amber-400" /> Market Insight
            </h2>
            <MarketInsightCard insight={latestInsight} />
          </div>

          {/* AI Recommendation Focus */}
          <div className="flex flex-col h-full gap-2">
            <h2 className="text-[10px] uppercase tracking-widest text-slate-500 font-bold ml-1 flex items-center gap-1.5">
              <Target size={12} /> Structural Signal
            </h2>
            <RecommendationCard signal={latestRecommendation} />
          </div>

          {/* Safety & Risk */}
          <div className="glass-card p-4 border border-red-500/20 bg-red-500/5">
            <KillSwitch />
            {isStale && (
              <div className="mt-4 flex items-start gap-2 text-xs text-amber-500 bg-amber-500/10 p-2 rounded">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <p>Market data connection is delayed. AI execution is suspended until sync is restored.</p>
              </div>
            )}
          </div>

        </div>

        {/* 3. MAIN TRADING PANEL (Right Panel) */}
        <div className="md:col-span-8 xl:col-span-9 space-y-6 flex flex-col">
          
          {/* Active Positions */}
          <div className="glass-card flex-1 flex flex-col p-1">
            {/* Minimal Tab Header */}
            <div className="flex items-center gap-4 px-4 py-3 border-b border-white/5">
              <button className="text-xs font-bold text-teal-400 border-b-2 border-teal-400 pb-1 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-teal-400 rounded-full animate-pulse"></span>
                ACTIVE POSITIONS ({positions.length})
              </button>
              <button className="text-xs font-bold text-slate-500 hover:text-slate-300 pb-1 transition-colors">
                PENDING (0)
              </button>
              <button className="text-xs font-bold text-slate-500 hover:text-slate-300 pb-1 transition-colors">
                HISTORY
              </button>
            </div>

            {/* Position Grid */}
            <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4 content-start min-h-[300px]">
              {positions.length > 0 ? positions.map((pos) => {
                const current = price || latestTick?.price || pos.filled_price
                const isBuy = pos.direction === 'BUY'
                const pnl = isBuy ? current - pos.filled_price : pos.filled_price - current
                const isWin = pnl >= 0

                return (
                  <div key={pos.order_id} className="relative bg-slate-800/30 rounded border border-white/5 p-4 hover:border-white/10 transition-colors group">
                    <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l ${isBuy ? 'bg-teal-500' : 'bg-red-500'}`}></div>
                    
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="font-bold text-slate-100">{pos.symbol}</span>
                          <span className={`text-[9px] px-1.5 py-0.5 rounded uppercase font-bold tracking-wider ${isBuy ? 'bg-teal-500/20 text-teal-400' : 'bg-red-500/20 text-red-400'}`}>
                            {pos.direction}
                          </span>
                        </div>
                        <div className="text-[10px] text-slate-500">
                          Vol: {pos.lots || 1} • Entry: <span className="text-slate-300">{pos.filled_price}</span>
                        </div>
                      </div>
                      <div className={`text-lg font-black tracking-tight ${isWin ? 'text-teal-400' : 'text-red-400'}`}>
                        {isWin ? '+' : ''}{(pnl * 1000).toLocaleString('en-US', {minimumFractionDigits: 1})}
                      </div>
                    </div>

                    <div className="flex justify-between items-center text-[10px] font-bold text-slate-500 mb-4 bg-black/20 p-2 rounded">
                      <div className="flex flex-col">
                        <span className="uppercase text-[8px] tracking-widest opacity-50">Stop Loss</span>
                        <span className={pos.sl ? 'text-red-400' : ''}>{pos.sl || 'NONE'}</span>
                      </div>
                      <div className="flex flex-col text-right">
                        <span className="uppercase text-[8px] tracking-widest opacity-50">Take Profit</span>
                        <span className={pos.tp ? 'text-teal-400' : ''}>{pos.tp || 'NONE'}</span>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2">
                      <button className="col-span-1 py-1.5 rounded border border-white/10 text-[10px] font-bold text-slate-300 hover:bg-white/5 transition-colors">
                        SET SL/BE
                      </button>
                      <button className="col-span-1 py-1.5 rounded border border-white/10 text-[10px] font-bold text-slate-300 hover:bg-white/5 transition-colors">
                        TAKE 50%
                      </button>
                      <button className="col-span-1 py-1.5 rounded bg-red-500/10 border border-red-500/20 text-[10px] font-bold text-red-400 hover:bg-red-500/20 transition-colors flex items-center justify-center gap-1">
                        <Zap size={10} /> CLOSE
                      </button>
                    </div>
                  </div>
                )
              }) : (
                <div className="col-span-full h-full min-h-[200px] flex flex-col items-center justify-center opacity-40">
                  <Briefcase size={32} className="mb-2 text-slate-500" />
                  <p className="text-sm font-medium text-slate-400">No active positions</p>
                </div>
              )}
            </div>
          </div>

        </div>

      </div>

      {/* 4. LOWER SUPPORTING PANEL */}
      <div className="grid grid-cols-1">
        <h2 className="text-[10px] uppercase tracking-widest text-slate-500 font-bold ml-1 mb-2">Detailed Execution Logs</h2>
        <AgentLog entries={logs} />
      </div>

    </div>
  )
}
