// frontend/src/pages/Settings.tsx
// Configuration page for API keys, risk limits, and paper/live toggles.

import React, { useState } from 'react'
import { Save, Shield, Sliders, AlertCircle, Bot, Bell } from 'lucide-react'

// ── Sub-components ────────────────────────────────────────────────────────────
function Section({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) {
  return (
    <div className="glass-card p-6 space-y-4">
      <div className="flex items-center gap-2 mb-2 text-teal-400">
        <Icon size={18} />
        <h2 className="text-sm font-bold uppercase tracking-wider">{title}</h2>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  )
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <label className="text-[10px] font-bold text-slate-500 uppercase">{label}</label>
      <div className="mt-1">{children}</div>
      {hint && <p className="text-[10px] text-slate-600 mt-1">{hint}</p>}
    </div>
  )
}

const inputClass = "w-full bg-slate-900/50 border border-slate-800 rounded px-3 py-2 text-sm text-slate-300 mt-1 focus:border-teal-500/50 outline-none transition-colors"

// ── Page ──────────────────────────────────────────────────────────────────────
export default function Settings() {
  const [config, setConfig] = useState({
    geminiKey: '••••••••••••••••',
    paperMode: true,
    maxPositionSize: 1,
    dailyStopLoss: 2.0,
    interval: 30
  })

  const [saved, setSaved] = useState(false)

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in pb-12">
      <div className="flex items-center justify-between pb-4 border-b border-white/5">
        <div>
          <h1 className="text-xl font-bold text-slate-200">System Configuration</h1>
          <p className="text-xs text-slate-500 mt-1">Manage your AI keys and algorithmic risk gates</p>
        </div>
        <button 
          onClick={handleSave}
          className="btn-primary flex items-center gap-2"
        >
          <Save size={16} />
          {saved ? 'Saved!' : 'Save Changes'}
        </button>
      </div>

      {/* AI & Automation */}
      <Section icon={Bot} title="AI & Automation">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Google Gemini API Key">
            <input 
              type="password" 
              value={config.geminiKey}
              onChange={e => setConfig({...config, geminiKey: e.target.value})}
              className={inputClass}
            />
          </Field>
          <Field label="Analysis Interval (sec)">
            <input 
              type="number" 
              value={config.interval}
              onChange={e => setConfig({...config, interval: parseInt(e.target.value) || 30})}
              className={inputClass}
            />
          </Field>
        </div>
        <div className="flex items-center gap-2 p-3 bg-teal-500/5 rounded border border-teal-500/10">
          <AlertCircle size={14} className="text-teal-500" />
          <p className="text-[10px] text-teal-500/80">API keys are required for the AI Client to perform real-time market analysis.</p>
        </div>
      </Section>

      {/* Risk Gate */}
      <Section icon={Shield} title="Risk Management">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Max Pos Size (Contracts)" hint="Limit per trade">
            <input 
              type="number" 
              value={config.maxPositionSize}
              onChange={e => setConfig({...config, maxPositionSize: parseInt(e.target.value) || 1})}
              className={inputClass}
            />
          </Field>
          <Field label="Daily Drawdown Limit (%)" hint="Killswitch threshold">
            <input 
              type="number" 
              value={config.dailyStopLoss}
              onChange={e => setConfig({...config, dailyStopLoss: parseFloat(e.target.value) || 2.0})}
              className={inputClass}
            />
          </Field>
        </div>

        <div className="flex items-center justify-between p-3 bg-red-500/5 rounded border border-red-500/10 mt-2">
          <div className="flex items-center gap-2">
            <Sliders size={14} className="text-red-400" />
            <span className="text-xs text-slate-300">TCBS Paper Trading Mode</span>
          </div>
          <div className="relative inline-flex items-center cursor-pointer">
            <input 
              type="checkbox" 
              checked={config.paperMode} 
              onChange={e => setConfig({...config, paperMode: e.target.checked})}
              className="sr-only peer" 
            />
            <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-teal-500"></div>
          </div>
        </div>
      </Section>

      {/* Notifications */}
      <Section icon={Bell} title="Notifications">
        <div className="opacity-40 select-none">
          <Field label="Telegram Bot Token">
            <input type="password" placeholder="Future release..." className={inputClass} disabled />
          </Field>
        </div>
      </Section>
    </div>
  )
}
