// frontend/src/App.tsx
// Root application component with React Router v6 and sidebar navigation.
// Dark glassmorphism layout: sidebar + main content area.

import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Zap, BarChart2, Settings, Activity,
  AlertTriangle, Wifi, WifiOff
} from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Signals from './pages/Signals'
import Backtest from './pages/Backtest'
import SettingsPage from './pages/Settings'
import { useWebSocket } from './hooks/useWebSocket'

// ── Sidebar navigation items ──────────────────────────────────────────────────
const NAV_ITEMS = [
  { path: '/',         label: 'Dashboard', icon: LayoutDashboard },
  { path: '/signals',  label: 'Signals',   icon: Zap             },
  { path: '/backtest', label: 'Backtest',  icon: BarChart2       },
  { path: '/settings', label: 'Settings',  icon: Settings        },
]

// ── Sidebar component ─────────────────────────────────────────────────────────
function Sidebar({ isConnected }: { isConnected: boolean }) {
  return (
    <aside className="fixed left-0 top-0 h-full w-56 flex flex-col py-6 px-3 z-10"
           style={{ background: 'rgba(6, 12, 25, 0.95)', borderRight: '1px solid rgba(45,212,191,0.08)' }}>
      {/* Logo */}
      <div className="px-3 mb-8">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{ background: 'linear-gradient(135deg, #0d9488, #14b8a6)' }}>
            <Activity size={16} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-bold text-teal-300">VN AI Trader</p>
            <p className="text-[10px] text-slate-500">v1.0.0 · Phase 6 Complete</p>
          </div>
        </div>
      </div>

      {/* Nav links */}
      <nav className="flex-1 flex flex-col gap-1">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Icon size={16} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Connection status */}
      <div className="px-3 pt-4 border-t" style={{ borderColor: 'rgba(45,212,191,0.08)' }}>
        <div className="flex items-center gap-2 text-xs">
          {isConnected
            ? <><span className="live-dot" /><span className="text-teal-400">Connected</span></>
            : <><WifiOff size={12} className="text-red-400" /><span className="text-red-400">Disconnected</span></>
          }
        </div>
        <p className="text-[10px] text-slate-600 mt-1">ws://localhost:8000/ws</p>
      </div>
    </aside>
  )
}

// ── Main layout ───────────────────────────────────────────────────────────────
function Layout() {
  const { isConnected } = useWebSocket('ws://localhost:8000/ws')

  return (
    <div className="min-h-screen flex">
      <Sidebar isConnected={isConnected} />
      <main className="flex-1 ml-56 p-6 overflow-auto">
        <Routes>
          <Route path="/"         element={<Dashboard />} />
          <Route path="/signals"  element={<Signals />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}

// ── App root ──────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  )
}
