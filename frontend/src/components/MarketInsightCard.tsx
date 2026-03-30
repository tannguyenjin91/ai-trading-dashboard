// frontend/src/components/MarketInsightCard.tsx
// Renders the rich MarketSummary structured output from the AI pipeline.

import { TrendingUp, TrendingDown, Minus, Zap, ShieldAlert, Target, Database, AlertTriangle } from 'lucide-react'

interface FibLevel {
  level: number
  price: number
}

export interface MarketInsightData {
  regime: 'TRENDING_UP' | 'TRENDING_DOWN' | 'CHOPPY' | 'VOLATILE'
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  one_liner: string
  current_price: number
  price_change: number
  price_change_pct: number
  period_high: number
  period_low: number
  trend_short: string
  trend_medium: string
  momentum: 'STRONG' | 'MODERATE' | 'WEAK'
  supports: number[]
  resistances: number[]
  swing_high: number
  swing_low: number
  fibonacci_levels: FibLevel[]
  nearest_fib_zone: string
  rsi: number
  macd_hist: number
  adx: number
  atr: number
  volume_ratio: number
  ema9: number
  ema21: number
  price_vs_ema9: 'ABOVE' | 'BELOW' | 'AT'
  price_vs_ema21: 'ABOVE' | 'BELOW' | 'AT'
  supertrend_dir: number
  scenario_bullish: string
  scenario_bearish: string
  risk_note: string
  confidence: number
  // Data quality fields
  data_quality?: 'full' | 'partial' | 'price_action_only'
  missing_indicators?: string[]
  ai_source?: string
  bars_used?: number
}

const BIAS_CONFIG = {
  BULLISH: { color: 'text-teal-400', bg: 'bg-teal-500/10 border-teal-500/20', icon: TrendingUp, label: 'BULLISH' },
  BEARISH: { color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/20', icon: TrendingDown, label: 'BEARISH' },
  NEUTRAL: { color: 'text-slate-400', bg: 'bg-slate-500/10 border-slate-500/20', icon: Minus, label: 'NEUTRAL' },
}

const REGIME_COLOR: Record<string, string> = {
  TRENDING_UP: 'text-teal-400 bg-teal-500/10',
  TRENDING_DOWN: 'text-red-400 bg-red-500/10',
  CHOPPY: 'text-amber-400 bg-amber-500/10',
  VOLATILE: 'text-orange-400 bg-orange-500/10',
}

const KEY_FIB_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]

function IndicatorPill({ label, value, good }: { label: string; value: string; good?: boolean | null }) {
  const colorClass = good === true ? 'text-teal-300' : good === false ? 'text-red-300' : 'text-slate-300'
  return (
    <div className="flex justify-between items-center text-[10px] py-0.5">
      <span className="text-slate-500 uppercase tracking-wider">{label}</span>
      <span className={`font-mono font-bold ${colorClass}`}>{value}</span>
    </div>
  )
}

function LevelBadge({ price, type }: { price: number; type: 'support' | 'resistance' }) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold font-mono ${
      type === 'support'
        ? 'bg-teal-500/15 text-teal-300 border border-teal-500/20'
        : 'bg-red-500/15 text-red-300 border border-red-500/20'
    }`}>
      {price.toLocaleString('en-US', { minimumFractionDigits: 0 })}
    </span>
  )
}

export default function MarketInsightCard({ insight }: { insight: MarketInsightData | null }) {
  if (!insight) {
    return (
      <div className="glass-card p-4 border border-teal-500/20 bg-teal-500/5 min-h-[120px] flex items-center justify-center">
        <div className="text-center text-xs text-slate-500 animate-pulse">
          <Zap size={16} className="mx-auto mb-2 text-slate-600" />
          AI đang phân tích thị trường...
        </div>
      </div>
    )
  }

  const biasConfig = BIAS_CONFIG[insight.bias] || BIAS_CONFIG.NEUTRAL
  const BiasIcon = biasConfig.icon
  const keyFibs = (insight.fibonacci_levels || []).filter(f => KEY_FIB_LEVELS.includes(f.level))
  const currentPrice = insight.current_price || 0

  return (
    <div className="glass-card overflow-hidden border border-white/5">
      {/* ── HEADER BAR ─────────────────────────────────────────────── */}
      <div className={`flex items-center justify-between px-4 py-2.5 border-b border-white/5 ${biasConfig.bg}`}>
        <div className="flex items-center gap-2">
          <BiasIcon size={13} className={biasConfig.color} />
          <span className={`text-[10px] font-bold tracking-widest uppercase ${biasConfig.color}`}>
            {biasConfig.label}
          </span>
          <span className={`ml-1 px-1.5 py-0.5 rounded text-[9px] font-semibold ${REGIME_COLOR[insight.regime] || 'text-slate-400'}`}>
            {insight.regime}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Data Quality Badge */}
          {insight.data_quality && (
            <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider ${
              insight.data_quality === 'full' ? 'bg-teal-500/15 text-teal-400 border border-teal-500/20' :
              insight.data_quality === 'partial' ? 'bg-amber-500/15 text-amber-400 border border-amber-500/20' :
              'bg-red-500/15 text-red-400 border border-red-500/20'
            }`}>
              <Database size={8} className="inline mr-0.5" />
              {insight.data_quality === 'full' ? 'Full Data' : insight.data_quality === 'partial' ? 'Partial' : 'Price Only'}
            </span>
          )}
          {insight.ai_source && (
            <span className="px-1.5 py-0.5 rounded text-[8px] font-bold bg-violet-500/15 text-violet-400 border border-violet-500/20 uppercase">
              {insight.ai_source}
            </span>
          )}
          <span className="text-[9px] text-slate-500 uppercase tracking-wider">Confidence</span>
          <span className={`text-xs font-bold ${insight.confidence >= 65 ? 'text-teal-400' : insight.confidence >= 45 ? 'text-amber-400' : 'text-red-400'}`}>
            {insight.confidence}%
          </span>
        </div>
      </div>

      <div className="p-4 space-y-3.5">
        {/* ── DATA QUALITY WARNING ────────────────────────────────── */}
        {insight.data_quality && insight.data_quality !== 'full' && (
          <div className={`flex items-start gap-1.5 rounded p-2 text-[10px] ${
            insight.data_quality === 'partial'
              ? 'bg-amber-500/5 border border-amber-500/15 text-amber-300/80'
              : 'bg-red-500/5 border border-red-500/15 text-red-300/80'
          }`}>
            <AlertTriangle size={11} className="mt-0.5 shrink-0" />
            <div>
              <span className="font-bold">
                {insight.data_quality === 'partial' ? 'Dữ liệu kỹ thuật không đầy đủ' : 'Chỉ có dữ liệu Price Action'}
              </span>
              {insight.missing_indicators && insight.missing_indicators.length > 0 && (
                <span className="ml-1 opacity-70">— Thiếu: {insight.missing_indicators.join(', ')}</span>
              )}
              {insight.bars_used && (
                <span className="ml-1 opacity-50">({insight.bars_used} nến)</span>
              )}
            </div>
          </div>
        )}

        {/* ── ONE-LINER ─────────────────────────────────────────────── */}
        {insight.one_liner && (
          <p className="text-xs text-slate-200 leading-relaxed font-medium border-l-2 border-teal-500/40 pl-3">
            {insight.one_liner}
          </p>
        )}

        {/* ── PRICE CONTEXT ─────────────────────────────────────────── */}
        <div className="grid grid-cols-3 gap-2">
          <div className="col-span-1">
            <p className="text-[9px] text-slate-500 uppercase tracking-widest mb-0.5">Giá</p>
            <p className="text-sm font-bold font-mono text-slate-100">
              {currentPrice.toLocaleString('en-US', { minimumFractionDigits: 1 })}
            </p>
            <p className={`text-[10px] font-bold ${insight.price_change_pct >= 0 ? 'text-teal-400' : 'text-red-400'}`}>
              {insight.price_change_pct > 0 ? '+' : ''}{insight.price_change_pct?.toFixed(2)}%
            </p>
          </div>
          <div className="col-span-1">
            <p className="text-[9px] text-slate-500 uppercase tracking-widest mb-0.5">Trend</p>
            <p className="text-[10px] font-bold text-slate-300">{insight.trend_short}</p>
            <p className="text-[9px] text-slate-500">{insight.trend_medium} (mid)</p>
          </div>
          <div className="col-span-1">
            <p className="text-[9px] text-slate-500 uppercase tracking-widest mb-0.5">Momentum</p>
            <p className={`text-[10px] font-bold ${
              insight.momentum === 'STRONG' ? 'text-teal-400' :
              insight.momentum === 'MODERATE' ? 'text-amber-400' : 'text-slate-400'
            }`}>{insight.momentum}</p>
          </div>
        </div>

        {/* ── KEY LEVELS (S/R) ─────────────────────────────────────── */}
        <div>
          <p className="text-[9px] text-slate-500 uppercase tracking-widest mb-1.5 flex items-center gap-1">
            <Target size={9} /> Vùng Quan Trọng
          </p>
          <div className="space-y-1">
            {insight.resistances?.length > 0 ? (
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[9px] text-red-400 w-14 shrink-0">Kháng cự</span>
                {insight.resistances.slice(0, 3).map((r, i) => (
                  <LevelBadge key={i} price={r} type="resistance" />
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <span className="text-[9px] text-red-400 w-14 shrink-0">Kháng cự</span>
                <span className="text-[9px] text-slate-600 italic">Chưa đủ dữ liệu (cần ≥42 nến)</span>
              </div>
            )}
            {insight.supports?.length > 0 ? (
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[9px] text-teal-400 w-14 shrink-0">Hỗ trợ</span>
                {insight.supports.slice(0, 3).map((s, i) => (
                  <LevelBadge key={i} price={s} type="support" />
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <span className="text-[9px] text-teal-400 w-14 shrink-0">Hỗ trợ</span>
                <span className="text-[9px] text-slate-600 italic">Chưa đủ dữ liệu (cần ≥42 nến)</span>
              </div>
            )}
          </div>
        </div>

        {/* ── FIBONACCI ─────────────────────────────────────────────── */}
        <div>
          <p className="text-[9px] text-slate-500 uppercase tracking-widest mb-1.5">
            Fibonacci {keyFibs.length > 0 && `(Swing: ${insight.swing_low?.toLocaleString()} — ${insight.swing_high?.toLocaleString()})`}
          </p>
          {keyFibs.length > 0 ? (
            <>
              <div className="flex flex-wrap gap-1">
                {keyFibs.map((fl) => {
                  const isNearest = insight.nearest_fib_zone?.includes(fl.level.toFixed(3))
                  return (
                    <div key={fl.level} className={`px-1.5 py-0.5 rounded text-[9px] font-mono border ${
                      isNearest
                        ? 'bg-amber-500/20 border-amber-500/40 text-amber-300 font-bold'
                        : 'bg-slate-800/60 border-white/5 text-slate-400'
                    }`}>
                      {(fl.level * 100).toFixed(1)}% · {fl.price.toLocaleString('en-US', { minimumFractionDigits: 1 })}
                    </div>
                  )
                })}
              </div>
              {insight.nearest_fib_zone && (
                <p className="text-[9px] text-amber-400/80 mt-1">📍 Gần nhất: {insight.nearest_fib_zone}</p>
              )}
            </>
          ) : (
            <p className="text-[9px] text-slate-600 italic">Chưa đủ dữ liệu (cần ≥30 nến)</p>
          )}
        </div>

        {/* ── INDICATOR GRID ────────────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-x-4 border-t border-white/5 pt-3">
          <div>
            <IndicatorPill label="RSI 14" value={insight.rsi?.toFixed(1)} good={insight.rsi > 30 && insight.rsi < 70 ? null : insight.rsi > 70 ? false : true} />
            <IndicatorPill label="MACD Hist" value={insight.macd_hist?.toFixed(3)} good={insight.macd_hist > 0 ? true : insight.macd_hist < 0 ? false : null} />
            <IndicatorPill label="ADX" value={insight.adx?.toFixed(1)} good={insight.adx > 25 ? true : null} />
          </div>
          <div>
            <IndicatorPill label="ATR" value={insight.atr?.toFixed(1)} />
            <IndicatorPill label="Vol Ratio" value={`${insight.volume_ratio?.toFixed(2)}x`} good={insight.volume_ratio > 0.8 ? true : false} />
            <IndicatorPill label="ST Dir" value={insight.supertrend_dir === 1 ? '▲ BULL' : insight.supertrend_dir === -1 ? '▼ BEAR' : '—'} good={insight.supertrend_dir === 1 ? true : insight.supertrend_dir === -1 ? false : null} />
          </div>
        </div>
        <div className="text-[9px] text-slate-600 space-y-0.5">
          <span>EMA9 {insight.ema9?.toFixed(1)} ({insight.price_vs_ema9})</span>
          <span className="mx-2">·</span>
          <span>EMA21 {insight.ema21?.toFixed(1)} ({insight.price_vs_ema21})</span>
        </div>

        {/* ── SCENARIOS ─────────────────────────────────────────────── */}
        {(insight.scenario_bullish || insight.scenario_bearish) && (
          <div className="space-y-1.5 border-t border-white/5 pt-3">
            {insight.scenario_bullish && (
              <div className="flex items-start gap-1.5">
                <span className="text-teal-500 text-[10px] mt-0.5 shrink-0">📈</span>
                <p className="text-[10px] text-slate-400 leading-relaxed">{insight.scenario_bullish}</p>
              </div>
            )}
            {insight.scenario_bearish && (
              <div className="flex items-start gap-1.5">
                <span className="text-red-500 text-[10px] mt-0.5 shrink-0">📉</span>
                <p className="text-[10px] text-slate-400 leading-relaxed">{insight.scenario_bearish}</p>
              </div>
            )}
          </div>
        )}

        {/* ── RISK NOTE ─────────────────────────────────────────────── */}
        {insight.risk_note && (
          <div className="flex items-start gap-1.5 bg-amber-500/5 border border-amber-500/15 rounded p-2">
            <ShieldAlert size={11} className="text-amber-400 mt-0.5 shrink-0" />
            <p className="text-[10px] text-amber-300/80 leading-relaxed">{insight.risk_note}</p>
          </div>
        )}
      </div>
    </div>
  )
}
