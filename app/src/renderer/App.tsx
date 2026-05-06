import { HashRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { AlertCircle } from 'lucide-react'
import Sidebar from './components/Sidebar'
import Onboarding from './pages/Onboarding'
import Settings from './pages/Settings'
import QueryBuilder from './pages/QueryBuilder'
import Pipeline from './pages/Pipeline'
import Results from './pages/Results'
import History from './pages/History'
import { PipelineProvider } from './hooks/usePipeline'

declare global {
  interface Window {
    api: import('../preload/index').ElectronAPI
  }
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  )
}

function AppRoutes() {
  const [loading, setLoading] = useState(true)
  const [needsOnboarding, setNeedsOnboarding] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    window.api.settings.get().then((s) => {
      setNeedsOnboarding(!s.onboardingComplete)
      setLoading(false)
    })
  }, [])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return
      const tag = (document.activeElement as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      switch (e.key) {
        case 'n':
          e.preventDefault()
          navigate('/query')
          break
        case ',':
          e.preventDefault()
          navigate('/settings')
          break
        case 'h':
          e.preventDefault()
          navigate('/history')
          break
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [navigate])

  if (loading)
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
      </div>
    )

  return (
    <Routes>
      <Route
        path="/"
        element={needsOnboarding ? <Navigate to="/onboarding" /> : <Navigate to="/query" />}
      />
      <Route path="/onboarding" element={<Onboarding />} />
      <Route
        path="/query"
        element={
          <Layout>
            <QueryBuilder />
          </Layout>
        }
      />
      <Route
        path="/pipeline"
        element={
          <Layout>
            <Pipeline />
          </Layout>
        }
      />
      <Route
        path="/results"
        element={
          <Layout>
            <Results />
          </Layout>
        }
      />
      <Route
        path="/history"
        element={
          <Layout>
            <History />
          </Layout>
        }
      />
      <Route
        path="/settings"
        element={
          <Layout>
            <Settings />
          </Layout>
        }
      />
    </Routes>
  )
}

function SetupScreen({
  logs,
  message,
  error,
}: {
  logs: string[]
  message: string
  error: string | null
}) {
  const terminalRef = useRef<HTMLDivElement>(null)
  // Stall detector — if no progress message or log line lands within 30s,
  // surface a "may be stuck" recovery UI so the user isn't staring at a
  // spinner forever when Python setup hangs or the main process died.
  const [stalled, setStalled] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setStalled(true), 30_000)
    return () => clearTimeout(timer)
  }, [logs.length, message])

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
    }
  }, [logs])

  return (
    <div className="h-screen w-screen bg-[#0a0a0f] flex flex-col overflow-hidden relative">
      {/* Terminal background — full screen, scrolling output */}
      <div
        ref={terminalRef}
        className="absolute inset-0 overflow-auto p-6 pt-48 pb-32 font-mono text-xs leading-relaxed"
      >
        {logs.map((line, i) => {
          let color = 'text-[#3a3a4a]'
          if (line.startsWith('$')) color = 'text-[#4a4a5a]'
          else if (line.includes('✓')) color = 'text-emerald-800/40'
          else if (line.startsWith('[')) color = 'text-indigo-800/30'
          else if (line.startsWith('Collecting') || line.startsWith('Downloading'))
            color = 'text-[#2a2a3a]'
          else if (line.startsWith('Installing') || line.startsWith('Successfully'))
            color = 'text-emerald-900/30'

          return (
            <div key={i} className={color}>
              {line}
            </div>
          )
        })}
        {!error && (
          <div className="text-[#4a4a5a] animate-pulse">
            {'> _'}
          </div>
        )}
      </div>

      {/* Gradient overlays for depth */}
      <div className="absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-[#0a0a0f] via-[#0a0a0f]/95 to-transparent pointer-events-none" />
      <div className="absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-[#0a0a0f] via-[#0a0a0f]/90 to-transparent pointer-events-none" />

      {/* Centered brand overlay */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <div className="pointer-events-auto flex flex-col items-center">
          {/* Logo */}
          <div className="w-24 h-24 mb-8 rounded-3xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center backdrop-blur-sm">
            <span className="text-5xl">🔬</span>
          </div>

          {/* Title */}
          <h1 className="text-2xl font-bold text-white/90 tracking-tight mb-1">
            ResearchShop
          </h1>
          <p className="text-sm text-white/30 mb-8">Desktop</p>

          {error ? (
            <div className="max-w-sm text-center">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-red-500/10 border border-red-500/20 mb-4">
                <AlertCircle className="w-4 h-4 text-red-400" />
                <span className="text-sm text-red-300">Setup Failed</span>
              </div>
              <p className="text-xs text-white/40 leading-relaxed mb-4">{error}</p>
              <p className="text-xs text-white/20">
                Install Python 3.9+ and restart the app.
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center">
              {/* Spinner */}
              <div className="relative w-10 h-10 mb-6">
                <div className="absolute inset-0 rounded-full border-2 border-white/[0.06]" />
                <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-indigo-500/60 animate-spin" />
              </div>

              {/* Status message */}
              <p className="text-sm text-white/50 font-medium">{message || 'Initializing...'}</p>

              {/* Stall recovery — appears after 30s of silence */}
              {stalled && (
                <div className="mt-6 max-w-sm text-center space-y-3">
                  <p className="text-xs text-amber-300/70">
                    Setup is taking longer than expected. The Python environment may be stuck.
                  </p>
                  <button
                    onClick={() => window.location.reload()}
                    className="text-xs text-white/60 hover:text-white/90 underline transition-colors"
                  >
                    Reload window
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Bottom version tag */}
      <div className="absolute bottom-4 left-0 right-0 text-center pointer-events-none">
        <span className="text-[10px] text-white/10 font-mono">v1.0.1</span>
      </div>
    </div>
  )
}

function App() {
  const [pythonReady, setPythonReady] = useState(false)
  const [pythonError, setPythonError] = useState<string | null>(null)
  const [setupMessage, setSetupMessage] = useState('')
  const [logs, setLogs] = useState<string[]>([])

  useEffect(() => {
    const removeProgress = window.api.pythonSetup.onProgress((data) => {
      setSetupMessage(data.message)
    })
    const removeLog = window.api.pythonSetup.onLog((line) => {
      setLogs((prev) => [...prev, line])
    })
    const removeComplete = window.api.pythonSetup.onComplete((data) => {
      if (data.ready) {
        setPythonReady(true)
      } else {
        setPythonError(data.error || 'Unknown error during Python setup')
      }
    })
    return () => {
      removeProgress()
      removeLog()
      removeComplete()
    }
  }, [])

  if (!pythonReady) {
    return (
      <SetupScreen logs={logs} message={setupMessage} error={pythonError} />
    )
  }

  return (
    <HashRouter>
      <PipelineProvider>
        <AppRoutes />
      </PipelineProvider>
    </HashRouter>
  )
}

export default App
