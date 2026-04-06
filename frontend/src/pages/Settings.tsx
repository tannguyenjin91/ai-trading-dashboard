import { useEffect, useState, type ElementType, type ReactNode } from 'react'
import { Bot, Database, Save, Settings2, SlidersHorizontal } from 'lucide-react'

const API_BASE = 'http://localhost:8000'

interface StrategySettingsPayload {
  symbol: string
  provider: 'VCI' | 'KBS'
  analysis_interval_sec: number
  history_window_days: number
  history_sync_interval_sec: number
  ai_enabled: boolean
  ai_model: string
  min_confidence: number
  risk_per_trade_pct: number
  initial_capital: number
  max_open_positions: number
  slippage_bps: number
  fee_bps: number
  allow_short: boolean
  auto_journal_signals: boolean
  notes: string
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: ElementType
  title: string
  children: ReactNode
}) {
  return (
    <div className="glass-card p-6 space-y-4">
      <div className="mb-2 flex items-center gap-2 text-teal-400">
        <Icon size={18} />
        <h2 className="text-sm font-bold uppercase tracking-wider">{title}</h2>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  )
}

function Field({
  label,
  children,
  hint,
}: {
  label: string
  children: ReactNode
  hint?: string
}) {
  return (
    <div>
      <label className="text-[10px] font-bold uppercase text-slate-500">{label}</label>
      <div className="mt-1">{children}</div>
      {hint && <p className="mt-1 text-[10px] text-slate-600">{hint}</p>}
    </div>
  )
}

const inputClass =
  'mt-1 w-full rounded border border-slate-800 bg-slate-900/50 px-3 py-2 text-sm text-slate-300 outline-none transition-colors focus:border-teal-500/50'

export default function Settings() {
  const [config, setConfig] = useState<StrategySettingsPayload | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const response = await fetch(`${API_BASE}/v1/market/strategy-settings`)
        if (!response.ok) return
        const data: StrategySettingsPayload = await response.json()
        if (active) setConfig(data)
      } catch (error) {
        console.error('Failed to load strategy settings:', error)
      }
    })()

    return () => {
      active = false
    }
  }, [])

  const handleSave = async () => {
    if (!config) return
    try {
      setIsSaving(true)
      const response = await fetch(`${API_BASE}/v1/market/strategy-settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      if (!response.ok) return
      const data: StrategySettingsPayload = await response.json()
      setConfig(data)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (error) {
      console.error('Failed to save strategy settings:', error)
    } finally {
      setIsSaving(false)
    }
  }

  if (!config) {
    return (
      <div className="glass-card p-6 text-sm text-slate-400">
        Loading strategy settings...
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-in pb-12">
      <div className="flex items-center justify-between border-b border-white/5 pb-4">
        <div>
          <h1 className="text-xl font-bold text-slate-200">AI Strategy Settings</h1>
          <p className="mt-1 text-xs text-slate-500">Configure signal generation, journaling, and vnstock data preferences.</p>
        </div>
        <button type="button" onClick={handleSave} className="btn-primary flex items-center gap-2" disabled={isSaving}>
          <Save size={16} />
          {isSaving ? 'Saving...' : saved ? 'Saved' : 'Save changes'}
        </button>
      </div>

      <Section icon={Bot} title="AI Strategy">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Signal Symbol">
            <input
              value={config.symbol}
              onChange={(event) => setConfig({ ...config, symbol: event.target.value.toUpperCase() })}
              className={inputClass}
            />
          </Field>
          <Field label="AI Model">
            <input
              value={config.ai_model}
              onChange={(event) => setConfig({ ...config, ai_model: event.target.value })}
              className={inputClass}
            />
          </Field>
          <Field label="Analysis Interval (sec)">
            <input
              type="number"
              value={config.analysis_interval_sec}
              onChange={(event) => setConfig({ ...config, analysis_interval_sec: Number(event.target.value) || 300 })}
              className={inputClass}
            />
          </Field>
          <Field label="Min Confidence (%)">
            <input
              type="number"
              value={config.min_confidence}
              onChange={(event) => setConfig({ ...config, min_confidence: Number(event.target.value) || 0 })}
              className={inputClass}
            />
          </Field>
        </div>

        <div className="flex items-center justify-between rounded border border-teal-500/10 bg-teal-500/5 p-3">
          <div>
            <p className="text-sm font-semibold text-slate-200">AI narrative enrichment</p>
            <p className="text-[10px] text-slate-500">Keep the technical recommendation intact but let the LLM explain context and risk.</p>
          </div>
          <input
            type="checkbox"
            checked={config.ai_enabled}
            onChange={(event) => setConfig({ ...config, ai_enabled: event.target.checked })}
            className="h-4 w-4 accent-teal-500"
          />
        </div>
      </Section>

      <Section icon={Database} title="Data Provider">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Provider">
            <select
              value={config.provider}
              onChange={(event) => setConfig({ ...config, provider: event.target.value as 'VCI' | 'KBS' })}
              className={inputClass}
            >
              <option value="VCI">VCI</option>
              <option value="KBS">KBS</option>
            </select>
          </Field>
          <Field label="History Window (days)" hint="Target local cache depth used for replay and recommendation fallback">
            <input
              type="number"
              value={config.history_window_days}
              onChange={(event) => setConfig({ ...config, history_window_days: Number(event.target.value) || 30 })}
              className={inputClass}
            />
          </Field>
          <Field label="Sync Interval (sec)" hint="How often the backend tries to extend and refresh the local history cache">
            <input
              type="number"
              value={config.history_sync_interval_sec}
              onChange={(event) => setConfig({ ...config, history_sync_interval_sec: Number(event.target.value) || 1800 })}
              className={inputClass}
            />
          </Field>
          <Field label="Notes" hint="Internal notes for this strategy profile">
            <input
              value={config.notes}
              onChange={(event) => setConfig({ ...config, notes: event.target.value })}
              className={inputClass}
            />
          </Field>
        </div>
      </Section>

      <Section icon={SlidersHorizontal} title="Risk & Portfolio">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Initial Capital">
            <input
              type="number"
              value={config.initial_capital}
              onChange={(event) => setConfig({ ...config, initial_capital: Number(event.target.value) || 0 })}
              className={inputClass}
            />
          </Field>
          <Field label="Risk Per Trade (%)">
            <input
              type="number"
              step="0.1"
              value={config.risk_per_trade_pct}
              onChange={(event) => setConfig({ ...config, risk_per_trade_pct: Number(event.target.value) || 0 })}
              className={inputClass}
            />
          </Field>
          <Field label="Max Open Positions">
            <input
              type="number"
              value={config.max_open_positions}
              onChange={(event) => setConfig({ ...config, max_open_positions: Number(event.target.value) || 1 })}
              className={inputClass}
            />
          </Field>
          <Field label="Slippage / Fee (bps)">
            <div className="grid grid-cols-2 gap-3">
              <input
                type="number"
                value={config.slippage_bps}
                onChange={(event) => setConfig({ ...config, slippage_bps: Number(event.target.value) || 0 })}
                className={inputClass}
              />
              <input
                type="number"
                value={config.fee_bps}
                onChange={(event) => setConfig({ ...config, fee_bps: Number(event.target.value) || 0 })}
                className={inputClass}
              />
            </div>
          </Field>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="flex items-center justify-between rounded border border-white/5 bg-white/5 p-3">
            <div>
              <p className="text-sm font-semibold text-slate-200">Allow short signals</p>
              <p className="text-[10px] text-slate-500">Keep SELL recommendations eligible for backtest and journal.</p>
            </div>
            <input
              type="checkbox"
              checked={config.allow_short}
              onChange={(event) => setConfig({ ...config, allow_short: event.target.checked })}
              className="h-4 w-4 accent-teal-500"
            />
          </label>

          <label className="flex items-center justify-between rounded border border-white/5 bg-white/5 p-3">
            <div>
              <p className="text-sm font-semibold text-slate-200">Auto journal signals</p>
              <p className="text-[10px] text-slate-500">Create simulated positions for high-conviction recommendations.</p>
            </div>
            <input
              type="checkbox"
              checked={config.auto_journal_signals}
              onChange={(event) => setConfig({ ...config, auto_journal_signals: event.target.checked })}
              className="h-4 w-4 accent-teal-500"
            />
          </label>
        </div>
      </Section>

      <Section icon={Settings2} title="Profile Notes">
        <p className="text-xs leading-relaxed text-slate-400">
          These settings drive three flows at once: vnstock data selection, live recommendation cadence, and the simulated portfolio journal used by the dashboard.
        </p>
      </Section>
    </div>
  )
}
