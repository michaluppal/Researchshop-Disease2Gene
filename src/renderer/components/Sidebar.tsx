import { NavLink, useNavigate } from 'react-router-dom'
import { Search, Clock, Settings, Plus, FlaskConical } from 'lucide-react'
import { useEffect, useState } from 'react'

const mainNavItems = [
  { to: '/query', icon: Search, label: 'Query Builder' },
  { to: '/history', icon: Clock, label: 'History' },
]

export default function Sidebar() {
  const [version, setVersion] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    window.api.app.version().then(setVersion)
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
