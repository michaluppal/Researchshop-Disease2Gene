import { NavLink, useNavigate } from 'react-router-dom'
import { Search, Clock, Settings, Plus, FlaskConical, Sparkles, Download, RefreshCw, CheckCircle2 } from 'lucide-react'
import { useEffect, useState } from 'react'

const mainNavItems = [
  { to: '/query', icon: Search, label: 'Query Builder' },
  { to: '/history', icon: Clock, label: 'History' },
]

interface UpdateStatus {
  status: 'checking' | 'available' | 'not-available' | 'downloading' | 'downloaded' | 'error'
  version?: string
  percent?: number
  error?: string
}

export default function Sidebar() {
  const [version, setVersion] = useState('')
  const [usage, setUsage] = useState<{ used: number; limit: number } | null>(null)
  const [update, setUpdate] = useState<UpdateStatus | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    window.api.app.version().then(setVersion)
  }, [])

  useEffect(() => {
    window.api.gemini.getDailyUsage().then(({ used, limit }) => setUsage({ used, limit })).catch(() => { /* usage bar is non-critical */ })
    const cleanup = window.api.gemini.onUsageChanged(({ used, limit }) => setUsage({ used, limit }))
    return cleanup
  }, [])

  useEffect(() => {
    const cleanup = window.api.updater.onStatus((data) => setUpdate(data))
    return cleanup
  }, [])

  return (
    <div className="w-56 bg-white border-r border-slate-200 flex flex-col">
      <div className="p-5 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-brand-600" />
          <h1 className="text-xl font-bold text-brand-700">ResearchShop</h1>
        </div>
        <p className="text-xs text-slate-400 mt-0.5 ml-7">Desktop</p>
      </div>

      <div className="p-3 pb-0">
        <button
          onClick={() => navigate('/query')}
          className="flex items-center justify-center gap-2 w-full px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Query
        </button>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {mainNavItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150 ${
                isActive
                  ? 'bg-brand-50 text-brand-700 border-l-[3px] border-brand-600'
                  : 'text-slate-600 hover:bg-gray-100 hover:text-slate-900 border-l-[3px] border-transparent'
              }`
            }
          >
            <Icon className="w-4 h-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {usage !== null && (() => {
        const pct = usage.used / usage.limit
        const barColor = pct >= 0.95 ? 'bg-red-500' : pct >= 0.80 ? 'bg-amber-400' : 'bg-emerald-400'
        return (
          <div className="px-4 pb-3">
            <div className="flex items-center gap-1 mb-1.5">
              <Sparkles className="w-3 h-3 text-slate-400" />
              <span className="text-xs text-slate-400 font-medium">Gemini API</span>
            </div>
            <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${barColor}`}
                style={{ width: `${Math.min(100, pct * 100)}%` }}
              />
            </div>
            <p className="text-xs text-slate-400 mt-1 text-right">
              {usage.used.toLocaleString()} / {usage.limit.toLocaleString()} today
            </p>
          </div>
        )
      })()}

      {/* Update notification */}
      {update?.status === 'available' && (
        <div className="px-3 pb-3">
          <button
            onClick={() => window.api.updater.download()}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-50 border border-brand-200 text-sm text-brand-700 hover:bg-brand-100 transition-colors"
          >
            <Download className="w-4 h-4 flex-shrink-0" />
            <span className="flex-1 text-left">v{update.version} available</span>
          </button>
        </div>
      )}
      {update?.status === 'downloading' && (
        <div className="px-3 pb-3">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-700">
            <RefreshCw className="w-4 h-4 flex-shrink-0 animate-spin" />
            <span className="flex-1">Downloading… {update.percent ?? 0}%</span>
          </div>
        </div>
      )}
      {update?.status === 'downloaded' && (
        <div className="px-3 pb-3">
          <button
            onClick={() => window.api.updater.install()}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200 text-sm text-emerald-700 hover:bg-emerald-100 transition-colors"
          >
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span className="flex-1 text-left">Restart to update</span>
          </button>
        </div>
      )}

      <div className="p-3 pt-0 border-t border-slate-200">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150 mt-2 ${
              isActive
                ? 'bg-brand-50 text-brand-700 border-l-[3px] border-brand-600'
                : 'text-slate-600 hover:bg-gray-100 hover:text-slate-900 border-l-[3px] border-transparent'
            }`
          }
        >
          <Settings className="w-4 h-4" />
          Settings
        </NavLink>
        {version && (
          <p className="text-xs text-slate-400 mt-2 ml-3">v{version}</p>
        )}
      </div>
    </div>
  )
}
