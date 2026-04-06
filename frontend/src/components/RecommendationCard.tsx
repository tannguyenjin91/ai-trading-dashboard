// frontend/src/components/RecommendationCard.tsx
import React from 'react';
import { Activity, TrendingUp, TrendingDown, Target, ShieldAlert, Zap, Clock, Info } from 'lucide-react';

interface EntryZone {
  min_price: number;
  max_price: number;
}

export interface SignalRecommendation {
  signal_id: string;
  symbol: string;
  recommendation: 'BUY' | 'SELL' | 'HOLD' | 'WAIT';
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  confidence: number;
  current_price: number;
  entry_zone: EntryZone | null;
  stop_loss: number | null;
  take_profit_targets: number[];
  exit_strategy?: string;
  trailing_stop_timeframe?: string;
  trailing_stop_atr_multiplier?: number;
  trailing_stop_atr?: number | null;
  trailing_stop_offset?: number | null;
  supports: number[];
  resistances: number[];
  nearest_fib_zone: string;
  trend_short: string;
  momentum: string;
  mtf_bias_15m?: string;
  mtf_setup_5m?: string;
  mtf_timing_1m?: string;
  risk_reward_estimate: number;
  reasoning: string[];
  risk_note: string;
  generated_at: string;
}

const RecommendationCard: React.FC<{ signal: SignalRecommendation | null }> = ({ signal }) => {
  if (!signal) {
    return (
      <div className="glass-card p-6 flex flex-col items-center justify-center border-dashed border-slate-700 opacity-50 h-full min-h-[300px]">
        <Activity className="text-slate-600 mb-2" size={32} />
        <p className="text-sm text-slate-500">Waiting for Technical Signal Recommendation...</p>
      </div>
    );
  }

  const isBuy = signal.recommendation === 'BUY';
  const isSell = signal.recommendation === 'SELL';
  const isWait = signal.recommendation === 'WAIT' || signal.recommendation === 'HOLD';
  
  const headerBg = isBuy ? 'bg-teal-500/10' : isSell ? 'bg-red-500/10' : 'bg-slate-800/50';
  const textColor = isBuy ? 'text-teal-400' : isSell ? 'text-red-400' : 'text-slate-400';
  const borderColor = isBuy ? 'border-teal-500/20' : isSell ? 'border-red-500/20' : 'border-slate-700';

  const formatPrice = (p: number | null) => p ? p.toLocaleString() : 'N/A';

  return (
    <div className={`glass-card overflow-hidden animate-slide-up border ${borderColor} flex flex-col h-full`}>
      {/* Top Banner */}
      <div className={`h-1 w-full ${isBuy ? 'bg-teal-500' : isSell ? 'bg-red-500' : 'bg-slate-500'}`} />
      
      {/* Header Section */}
      <div className={`p-4 ${headerBg} flex justify-between items-center border-b ${borderColor}`}>
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg bg-slate-900 border ${borderColor}`}>
            {isBuy ? <TrendingUp className="text-teal-400" size={24} /> : 
             isSell ? <TrendingDown className="text-red-400" size={24} /> : 
             <Activity className="text-slate-400" size={24} />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className={`font-bold text-xl ${textColor} tracking-wider`}>
                {signal.recommendation}
              </h3>
              <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700">
                {signal.symbol}
              </span>
            </div>
            <p className="text-xs text-slate-400 flex items-center gap-1 mt-1">
              <Zap size={12} className={textColor} />
              Confidence: <span className="text-slate-200 font-mono">{(signal.confidence).toFixed(0)}%</span>
            </p>
          </div>
        </div>
        
        <div className="text-right">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Current Price</p>
          <p className="font-mono text-xl text-white font-bold">{formatPrice(signal.current_price)}</p>
          <div className="flex items-center justify-end gap-1 mt-1 text-[10px] text-slate-400">
             <Clock size={10} />
             {new Date(signal.generated_at).toLocaleTimeString()}
          </div>
        </div>
      </div>

      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4 flex-1">
        {/* Left Column: Actionable Levels (The Call) */}
        <div className="flex flex-col gap-3">
          <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1 border-b border-slate-800 pb-2">The Call</h4>
          
          <div className="bg-slate-900/60 p-3 rounded-lg border border-slate-800 flex justify-between items-center">
             <div>
               <p className="text-[10px] text-slate-500 uppercase mb-1">Entry Zone</p>
               {signal.entry_zone ? (
                 <p className="font-mono text-sm text-slate-200">
                   {formatPrice(signal.entry_zone.min_price)} <span className="text-slate-600">-</span> {formatPrice(signal.entry_zone.max_price)}
                 </p>
               ) : (
                 <p className="font-mono text-sm text-slate-500">N/A</p>
               )}
             </div>
             <div className="text-right">
                <p className="text-[10px] text-slate-500 uppercase mb-1">Bias</p>
                <p className={`text-xs font-bold ${signal.bias === 'BULLISH' ? 'text-teal-400' : signal.bias === 'BEARISH' ? 'text-red-400' : 'text-slate-400'}`}>
                  {signal.bias}
                </p>
             </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-red-950/20 p-3 rounded-lg border border-red-900/30">
              <div className="flex items-center gap-1.5 text-[10px] text-red-500/70 mb-1 uppercase font-bold">
                <ShieldAlert size={12} /> Stop Loss
              </div>
              <p className="text-sm font-mono text-red-400">{formatPrice(signal.stop_loss)}</p>
            </div>
            
            <div className="bg-teal-950/20 p-3 rounded-lg border border-teal-900/30">
              <div className="flex items-center gap-1.5 text-[10px] text-teal-500/70 mb-1 uppercase font-bold">
                <Target size={12} /> Target
              </div>
              <p className="text-sm font-mono text-teal-400">{formatPrice(signal.take_profit_targets?.[0])}</p>
            </div>
          </div>

          {!isWait && (signal.exit_strategy || signal.trailing_stop_offset) && (
            <div className="rounded-lg border border-cyan-500/20 bg-cyan-950/10 p-3">
              <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-cyan-300/80">Exit Plan</p>
              <p className="text-xs text-cyan-100/80">
                ATR trailing stop {signal.trailing_stop_timeframe || '10m'} x{(signal.trailing_stop_atr_multiplier ?? 2).toFixed(1)}
                {signal.trailing_stop_offset ? `, offset ~${formatPrice(signal.trailing_stop_offset)}` : ''}
                {signal.take_profit_targets?.[0] ? `, take profit map ${formatPrice(signal.take_profit_targets[0])}` : ''}
              </p>
            </div>
          )}

          {!isWait && signal.risk_reward_estimate > 0 && (
             <div className="text-right mt-auto">
               <span className="text-[10px] text-slate-500">Est. R:R Ratio: </span>
               <span className="text-xs font-mono text-slate-300">{signal.risk_reward_estimate.toFixed(2)}</span>
             </div>
          )}
        </div>

        {/* Right Column: Context & Reasoning */}
        <div className="flex flex-col gap-3">
          <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1 border-b border-slate-800 pb-2">Multi-Timeframe Alignment</h4>
          
          <div className="flex items-center justify-between gap-2 p-2 bg-slate-900/40 rounded-lg border border-slate-800/50">
            <div className="flex flex-col items-center text-center flex-1">
              <span className="text-[9px] text-slate-500 uppercase mb-1">Bias (15m)</span>
              <span className={`px-2 py-0.5 rounded text-[9px] font-bold ${signal.mtf_bias_15m === 'BULLISH' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20' : signal.mtf_bias_15m === 'BEARISH' ? 'bg-red-500/10 text-red-400 border border-red-500/20' : 'bg-slate-800 text-slate-400 border border-slate-700'}`}>
                {signal.mtf_bias_15m || 'N/A'}
              </span>
            </div>
            <div className="w-px h-6 bg-slate-800 shrink-0"></div>
            <div className="flex flex-col items-center text-center flex-1">
              <span className="text-[9px] text-slate-500 uppercase mb-1">Setup (5m)</span>
              <span className={`px-2 py-0.5 rounded text-[9px] font-bold ${signal.mtf_setup_5m === 'NEUTRAL' || !signal.mtf_setup_5m ? 'bg-slate-800 text-slate-400 border border-slate-700' : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'}`}>
                {signal.mtf_setup_5m ? signal.mtf_setup_5m.replace('_', ' ') : 'N/A'}
              </span>
            </div>
            <div className="w-px h-6 bg-slate-800 shrink-0"></div>
            <div className="flex flex-col items-center text-center flex-1">
              <span className="text-[9px] text-slate-500 uppercase mb-1">Timing (1m)</span>
              <span className={`px-2 py-0.5 rounded text-[9px] font-bold ${signal.mtf_timing_1m === 'CONFIRM_BUY' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20' : signal.mtf_timing_1m === 'CONFIRM_SELL' ? 'bg-red-500/10 text-red-400 border border-red-500/20' : 'bg-slate-800 text-slate-400 border border-slate-700'}`}>
                {signal.mtf_timing_1m ? signal.mtf_timing_1m.replace('_', ' ') : 'WAIT'}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 text-[10px] mt-1">
             <span className="px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">
               <span className="text-slate-500 mr-1">Trend:</span> {signal.trend_short}
             </span>
             <span className="px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">
               <span className="text-slate-500 mr-1">Mom:</span> {signal.momentum}
             </span>
             {signal.nearest_fib_zone && (
               <span className="px-2 py-1 rounded bg-indigo-900/30 text-indigo-300 border border-indigo-500/20">
                 Fib: {signal.nearest_fib_zone}
               </span>
             )}
          </div>

          <div className="bg-slate-900/40 p-3 rounded-lg border border-slate-800/50 flex flex-col gap-2 mt-1">
             <div className="flex items-start gap-2">
                <Info size={14} className="text-slate-500 mt-0.5 shrink-0" />
                <div className="text-xs text-slate-300 leading-relaxed">
                  {signal.reasoning.map((r, i) => <p key={i} className={i > 0 ? "mt-1" : ""}>{r}</p>)}
                </div>
             </div>
          </div>

          {signal.risk_note && (
             <div className="mt-auto bg-amber-950/20 p-3 rounded-lg border border-amber-500/20">
               <p className="text-[10px] text-amber-500/80 mb-1 font-bold uppercase tracking-wider">Risk Note</p>
               <p className="text-xs text-amber-200/70 italic">
                 "{signal.risk_note}"
               </p>
             </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RecommendationCard;
