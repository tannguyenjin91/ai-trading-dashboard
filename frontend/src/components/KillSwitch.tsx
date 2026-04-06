import { useState } from 'react'
import { AlertTriangle, PauseCircle, PlayCircle } from 'lucide-react'

const API_BASE = 'http://localhost:8000'

export default function KillSwitch() {
  const [showConfirm, setShowConfirm] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const toggleSignals = async (active: boolean) => {
    try {
      setIsSaving(true)
      const response = await fetch(`${API_BASE}/v1/monitor/kill-switch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active }),
      })
      if (response.ok) {
        setIsPaused(active)
        setShowConfirm(false)
      }
    } catch (error) {
      console.error('Failed to toggle signal pause:', error)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <>
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-100">Signal Pause</p>
          <p className="text-xs text-slate-400">
            {isPaused
              ? 'AI recommendation loops are paused. Existing journal positions stay untouched.'
              : 'Use this when you want to stop new recommendations and portfolio journaling.'}
          </p>
        </div>

        <button
          type="button"
          className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
            isPaused
              ? 'bg-teal-500/15 text-teal-300 border border-teal-500/20'
              : 'bg-red-500/15 text-red-300 border border-red-500/20'
          }`}
          onClick={() => (isPaused ? toggleSignals(false) : setShowConfirm(true))}
          disabled={isSaving}
        >
          {isPaused ? <PlayCircle size={14} /> : <PauseCircle size={14} />}
          {isPaused ? 'Resume AI' : 'Pause AI'}
        </button>
      </div>

      {showConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
        >
          <div className="glass-card w-full max-w-sm p-6 animate-slide-up">
            <div className="mb-3 flex items-center gap-3">
              <div className="rounded-lg bg-red-500/15 p-2">
                <AlertTriangle size={20} className="text-red-400" />
              </div>
              <h2 className="text-base font-bold text-slate-100">Pause AI signals?</h2>
            </div>
            <p className="mb-5 text-sm text-slate-400">
              This stops new recommendation cycles and prevents new journal entries. It does not delete history or close any simulated positions.
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                className="btn-kill flex-1"
                onClick={() => toggleSignals(true)}
                disabled={isSaving}
              >
                {isSaving ? 'Saving...' : 'Pause now'}
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl px-4 py-2 text-sm font-medium text-slate-300"
                style={{ background: 'rgba(100,116,139,0.1)', border: '1px solid rgba(100,116,139,0.2)' }}
                onClick={() => setShowConfirm(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
