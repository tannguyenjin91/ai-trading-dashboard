// frontend/src/components/KillSwitch.tsx
// Emergency stop button — prompts for confirmation then calls /api/killswitch.
// Colored red with glow. CRITICAL safety component.
// Phase 1: UI only — API integration in Phase 5.

import { useState } from 'react'
import { AlertTriangle, X, Zap } from 'lucide-react'

export default function KillSwitch() {
  const [showConfirm, setShowConfirm] = useState(false)
  const [triggered, setTriggered] = useState(false)

  const handleKill = async () => {
    try {
      const response = await fetch('http://localhost:8000/v1/monitor/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: true })
      })
      if (response.ok) {
        setTriggered(true)
        setShowConfirm(false)
        console.log('🚨 KILLSWITCH triggered — system paused')
      }
    } catch (err) {
      console.error('Failed to trigger KillSwitch:', err)
    }
  }

  if (triggered) {
    return (
      <div className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold text-red-100 animate-pulse"
           style={{ background: 'rgba(239,68,68,0.8)', boxShadow: '0 0 15px rgba(239,68,68,0.5)' }}>
        <AlertTriangle size={14} />
        KILLSWITCH ACTIVE
      </div>
    )
  }

  return (
    <>
      <button
        id="killswitch-btn"
        className="btn-kill flex items-center gap-2 text-sm"
        onClick={() => setShowConfirm(true)}
      >
        <AlertTriangle size={14} />
        KILL SWITCH
      </button>

      {/* Confirmation modal */}
      {showConfirm && (
        <div className="fixed inset-0 flex items-center justify-center z-50"
             style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}>
          <div className="glass-card p-6 max-w-sm w-full mx-4 animate-slide-up"
               style={{ borderColor: 'rgba(239,68,68,0.3)' }}>
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 rounded-lg bg-red-500/20">
                <AlertTriangle size={20} className="text-red-400" />
              </div>
              <h2 className="text-base font-bold text-red-400">Xác nhận KILLSWITCH</h2>
            </div>
            <p className="text-sm text-slate-400 mb-5">
              Hành động này sẽ <strong className="text-red-300">đóng TẤT CẢ vị thế ngay lập tức</strong> theo lệnh thị trường.
              Không thể hoàn tác.
            </p>
            <div className="flex gap-3">
              <button
                id="killswitch-confirm-btn"
                className="btn-kill flex-1 flex items-center justify-center gap-2"
                onClick={handleKill}
              >
                <Zap size={14} />
                Xác nhận đóng tất cả
              </button>
              <button
                className="flex-1 px-4 py-2 rounded-xl text-sm font-medium text-slate-400 transition-colors hover:text-slate-200"
                style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid rgba(100,116,139,0.2)' }}
                onClick={() => setShowConfirm(false)}
              >
                Hủy
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
