// frontend/src/components/SignalCard.tsx
// Component to display AI Agent trading signals.

import React from 'react';
import { Activity, TrendingUp, TrendingDown, Target, ShieldAlert } from 'lucide-react';

interface SignalData {
  action: 'LONG' | 'SHORT' | 'HOLD' | 'CLOSE';
  confidence: number;
  entry: number;
  stop_loss: number;
  take_profit: number[];
  rationale?: string;
  timestamp: string;
}

const SignalCard: React.FC<{ signal: SignalData | null }> = ({ signal }) => {
  if (!signal) {
    return (
      <div className="glass-card p-6 flex flex-col items-center justify-center border-dashed opacity-50">
        <Activity className="text-slate-700 mb-2" size={32} />
        <p className="text-xs text-slate-600">Waiting for AI signal...</p>
      </div>
    );
  }

  const isLong = signal.action === 'LONG';
  const isShort = signal.action === 'SHORT';

  return (
    <div className="glass-card overflow-hidden animate-slide-up">
      <div className={`h-1 w-full ${isLong ? 'bg-teal-500' : isShort ? 'bg-red-500' : 'bg-slate-700'}`} />
      <div className="p-4">
        <div className="flex justify-between items-start mb-4">
          <div className="flex items-center gap-2">
            <div className={`p-2 rounded-lg ${isLong ? 'bg-teal-500/10' : isShort ? 'bg-red-500/10' : 'bg-slate-800'}`}>
              {isLong ? <TrendingUp className="text-teal-400" size={20} /> : 
               isShort ? <TrendingDown className="text-red-400" size={20} /> : 
               <Activity className="text-slate-400" size={20} />}
            </div>
            <div>
              <h3 className={`font-bold text-lg ${isLong ? 'text-teal-400' : isShort ? 'text-red-400' : 'text-slate-400'}`}>
                {signal.action}
              </h3>
              <p className="text-[10px] text-slate-500">Confidence: {(signal.confidence * 100).toFixed(0)}%</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-500 uppercase">Entry Target</p>
            <p className="font-mono text-slate-200">{signal.entry.toLocaleString()}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
            <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-1">
              <ShieldAlert size={12} className="text-red-500" /> STOP LOSS
            </div>
            <p className="text-sm font-mono text-red-400/90 font-bold">{signal.stop_loss.toLocaleString()}</p>
          </div>
          <div className="bg-slate-900/50 p-2 rounded border border-slate-800">
            <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mb-1">
              <Target size={12} className="text-teal-500" /> TAKE PROFIT
            </div>
            <p className="text-sm font-mono text-teal-400/90 font-bold">{signal.take_profit?.[0]?.toLocaleString() || 'N/A'}</p>
          </div>
        </div>

        {signal.rationale && (
          <div className="bg-slate-950/40 p-3 rounded-lg border border-teal-500/5">
            <p className="text-[10px] text-teal-500/80 mb-1 font-bold">AI RATIONALE</p>
            <p className="text-xs text-slate-400 leading-relaxed italic">
              "{signal.rationale}"
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SignalCard;
