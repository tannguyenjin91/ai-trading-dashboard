// frontend/src/components/SafetyDeck.tsx
import { useState } from 'react'
import { Shield, ShieldAlert, AlertCircle } from 'lucide-react'

interface SafetyDeckProps {
  status: any | null
}

export default function SafetyDeck({ status }: SafetyDeckProps) {
  const [showLiveConfirm, setShowLiveConfirm] = useState(false)
  const isLiveEnabled = status?.is_live_trading_enabled || false
  const wsConnected = status?.stats?.ws_connected || false

  const handleToggleLive = async (targetState: boolean) => {
    try {
      if (targetState === true) {
        setShowLiveConfirm(true)
        return
      }
      await executeToggle(false)
    } catch (err) {
      console.error('Toggle live failed:', err)
    }
  }

  const executeToggle = async (active: boolean) => {
    const response = await fetch('http://localhost:8000/v1/monitor/toggle-live', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active })
    })
    if (response.ok) {
        setShowLiveConfirm(false)
    }
  }

  return (
    <div className="glass-card p-4 flex flex-col gap-4 min-w-[300px]">
      <div className="flex items-center justify-between border-b border-white/5 pb-2">
        <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
          <Shield size={14} /> Safety Control Deck
        </h3>
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${wsConnected ? 'bg-teal-500/10 text-teal-400' : 'bg-red-500/10 text-red-400'}`}>
          WS: {wsConnected ? 'ACTIVE' : 'OFFLINE'}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${isLiveEnabled ? 'bg-orange-500/20 text-orange-400' : 'bg-slate-500/10 text-slate-500'}`}>
            {isLiveEnabled ? <ShieldAlert size={20} /> : <Shield size={20} />}
          </div>
          <div>
            <p className="text-sm font-bold text-slate-200">Production Mode</p>
            <p className="text-[10px] text-slate-500">{isLiveEnabled ? 'REAL MONEY TRADES ACTIVE' : 'Paper Trading (Simulation)'}</p>
          </div>
        </div>
        
        <button
          onClick={() => handleToggleLive(!isLiveEnabled)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${isLiveEnabled ? 'bg-orange-600' : 'bg-slate-700'}`}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${isLiveEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
        <div className="p-2 rounded bg-white/5 border border-white/5">
          <p className="text-slate-600 mb-1">UPTIME</p>
          <p className="text-slate-300">{status?.uptime_sec ? `${Math.floor(status.uptime_sec / 60)}m ${status.uptime_sec % 60}s` : '---'}</p>
        </div>
        <div className="p-2 rounded bg-white/5 border border-white/5">
          <p className="text-slate-600 mb-1">REJECTIONS</p>
          <p className="text-slate-300">{status?.stats?.rejections_count || 0}</p>
        </div>
      </div>

      {showLiveConfirm && (
        <div className="fixed inset-0 flex items-center justify-center z-[100] px-4" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(8px)' }}>
          <div className="glass-card p-6 max-w-sm w-full border-orange-500/30 animate-scale-in">
            <div className="flex items-center gap-3 mb-4 text-orange-400">
                <AlertCircle size={24} />
                <h2 className="text-lg font-bold">WARNING: Live Trading</h2>
            </div>
            <p className="text-sm text-slate-400 mb-6 leading-relaxed">
                Bạn đang chuẩn bị kích hoạt <strong>CHẾ ĐỘ GIAO DỊCH THẬT</strong>. 
                Mọi lệnh từ AI sẽ được gửi trực tiếp lên sàn TCBS với 
                <span className="text-orange-300"> TIỀN THẬT</span>.
            </p>
            <div className="flex gap-3">
              <button 
                className="flex-1 btn-primary bg-orange-600 hover:bg-orange-500 text-white font-bold"
                onClick={() => executeToggle(true)}
              >
                Kích hoạt Live
              </button>
              <button 
                className="flex-1 px-4 py-2 rounded-xl text-sm font-medium text-slate-400 bg-white/5 hover:bg-white/10"
                onClick={() => setShowLiveConfirm(false)}
              >
                Hủy
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
