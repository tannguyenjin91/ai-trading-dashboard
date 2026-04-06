import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { Activity, BarChart2, LayoutDashboard, Settings, WifiOff, Zap } from 'lucide-react'

import Backtest from './pages/Backtest'
import Dashboard from './pages/Dashboard'
import SettingsPage from './pages/Settings'
import Signals from './pages/Signals'
import { useWebSocket } from './hooks/useWebSocket'

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/signals', label: 'Signals', icon: Zap },
  { path: '/backtest', label: 'Backtest', icon: BarChart2 },
  { path: '/settings', label: 'Settings', icon: Settings },
]

function Sidebar({ isConnected }: { isConnected: boolean }) {
  return (
    <aside
      className="fixed left-0 top-0 z-10 flex h-full w-56 flex-col px-3 py-6"
      style={{ background: 'rgba(6, 12, 25, 0.95)', borderRight: '1px solid rgba(45,212,191,0.08)' }}
    >
      <div className="mb-8 px-3">
        <div className="flex items-center gap-2">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-lg"
            style={{ background: 'linear-gradient(135deg, #0d9488, #14b8a6)' }}
          >
            <Activity size={16} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-bold text-teal-300">VN AI Signal Lab</p>
            <p className="text-[10px] text-slate-500">v1.1.0 | Signal Mode</p>
          </div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Icon size={16} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t px-3 pt-4" style={{ borderColor: 'rgba(45,212,191,0.08)' }}>
        <div className="flex items-center gap-2 text-xs">
          {isConnected ? (
            <>
              <span className="live-dot" />
              <span className="text-teal-400">Connected</span>
            </>
          ) : (
            <>
              <WifiOff size={12} className="text-red-400" />
              <span className="text-red-400">Disconnected</span>
            </>
          )}
        </div>
        <p className="mt-1 text-[10px] text-slate-600">ws://localhost:8000/ws</p>
      </div>
    </aside>
  )
}

function Layout() {
  const { isConnected } = useWebSocket('ws://localhost:8000/ws')

  return (
    <div className="flex min-h-screen">
      <Sidebar isConnected={isConnected} />
      <main className="ml-56 flex-1 overflow-auto p-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  )
}
