// frontend/src/pages/Dashboard.tsx
import { useState, useEffect } from 'react'
import { Activity, AlertCircle, Briefcase, Zap, Target } from 'lucide-react'
import { useWebSocket } from '../hooks/useWebSocket'
import { useMarketData } from '../hooks/useMarketData'
import KillSwitch from '../components/KillSwitch'
import AgentLog from '../components/AgentLog'
import RecommendationCard from '../components/RecommendationCard'
import MarketInsightCard from '../components/MarketInsightCard'

export default function Dashboard() {
  const { isConnected, latestStatus, latestTick, latestSignal, latestInsight, latestRecommendation, messages } = useWebSocket('ws://localhost:8000/ws')
  const { data: marketData, isLoading, isStale } = useMarketData('VN30F1M')
  
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

  // Aggregate derived stats based on real data
  const baseBalance = 50000.00 // Assuming base capital, will tie to API later
  const openPnL = positions.reduce((acc, p) => {
    const currentPrice = marketData?.price || latestTick?.price || p.filled_price
    const diff = p.direction === 'BUY' ? currentPrice - p.filled_price : p.filled_price - currentPrice
    return acc + (diff * 1000) // multiplier representation
  }, 0)
  
  const equity = baseBalance + openPnL
  const marginUsed = positions.length * 250 // mock margin block
  const freeMargin = equity - marginUsed
  const marginLevel = marginUsed > 0 ? (equity / marginUsed) * 100 : 0

  const formatTime = (ts?: number) => ts ? new Date(ts * 1000).toLocaleTimeString('vi-VN') : '--:--:--'
  const isHealthy = isConnected && !isStale

  // Helper for PnL styling
  const pnlColorClass = openPnL > 0 ? 'text-teal-400' : openPnL < 0 ? 'text-red-400' : 'text-slate-300'

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      
      {/* 1. TOP SUMMARY / MARKET BAR */}
      <div className="glass-card flex flex-col lg:flex-row lg:items-center justify-between p-4 gap-4 border-l-4 border-l-teal-500">
        
        {/* System & Market Status */}
        <div className="flex flex-wrap items-center gap-6">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-teal-500 animate-pulse' : 'bg-red-500'}`}></span>
            <span className={`text-sm font-bold tracking-wide uppercase ${isHealthy ? 'text-teal-400' : 'text-red-400'}`}>
              {isHealthy ? 'System Live' : 'System Degraded'}
            </span>
          </div>
          <div className="h-4 w-px bg-white/10 hidden lg:block"></div>
          
          {/* Core Symbol Quote */}
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-bold text-slate-100">VN30F1M</span>
            {isLoading ? (
              <span className="text-sm text-slate-500">Loading market...</span>
            ) : (
              <>
                <span className="text-2xl font-mono tracking-tight text-white">{marketData?.price ? marketData.price.toLocaleString('en-US', {minimumFractionDigits: 1}) : '---'}</span>
                <span className={`text-sm font-bold font-mono ${marketData?.change_pct && marketData.change_pct >= 0 ? 'text-teal-400' : 'text-red-400'}`}>
                  {marketData?.change_pct ? (marketData.change_pct > 0 ? '+' : '') + marketData.change_pct.toFixed(2) + '%' : ''}
                </span>
                <span className="text-xs text-slate-500 ml-2">Vol: {marketData?.volume ? (marketData.volume / 1000).toFixed(1) + 'K' : '---'}</span>
              </>
            )}
          </div>
        </div>

        {/* Info & Mode */}
        <div className="flex items-center gap-4 text-xs font-medium">
          <div className="text-slate-400 flex items-center gap-1.5">
            <Activity size={12} /> Sync: <span className="text-slate-200">{formatTime(marketData?.last_updated)}</span>
          </div>
          <div className={`px-3 py-1 rounded border ${latestStatus?.is_live_trading_enabled ? 'bg-amber-500/10 border-amber-500/30 text-amber-500' : 'bg-slate-800/50 border-slate-700 text-slate-400'}`}>
            {latestStatus?.is_live_trading_enabled ? 'LIVE TRADING' : 'PAPER TRADING'}
          </div>
        </div>
      </div>

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
                const current = marketData?.price || latestTick?.price || pos.filled_price
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
