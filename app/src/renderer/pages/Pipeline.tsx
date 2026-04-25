import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Square,
  AlertCircle,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  FileText,
  Dna,
  Filter,
  FlaskConical,
  Beaker,
  Clock,
} from 'lucide-react'
import { usePipeline, StructuredLog } from '../hooks/usePipeline'
import PipelineSteps from '../components/PipelineSteps'

function LogLevelIcon({ level }: { level: string }) {
  if (level === 'error') return <span className="text-red-500 mr-2 flex-shrink-0">&#x2717;</span>
  if (level === 'warn') return <span className="text-amber-500 mr-2 flex-shrink-0">&#x26A0;</span>
  return <span className="text-emerald-500 mr-2 flex-shrink-0">&#x2022;</span>
}

function formatTime(timestamp: string): string {
  try {
    const d = new Date(timestamp)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

export default function Pipeline() {
  const navigate = useNavigate()
  const { stage, percent, stats, result, isRunning, error, logs, structuredLogs, cancel } =
    usePipeline()
  const userLogRef = useRef<HTMLDivElement>(null)
  const techLogRef = useRef<HTMLDivElement>(null)
  const [showTechnical, setShowTechnical] = useState(false)
  const [geminiUsage, setGeminiUsage] = useState<{ used: number; limit: number; date: string } | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const elapsedIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Elapsed time counter
  useEffect(() => {
    if (isRunning) {
      setElapsedSeconds(0)
      elapsedIntervalRef.current = setInterval(() => {
        setElapsedSeconds((s) => s + 1)
      }, 1000)
    } else if (elapsedIntervalRef.current) {
      clearInterval(elapsedIntervalRef.current)
      elapsedIntervalRef.current = null
    }
    return () => {
      if (elapsedIntervalRef.current) clearInterval(elapsedIntervalRef.current)
    }
  }, [isRunning])

  const formatElapsed = (seconds: number) => {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }

  const refreshUsage = useCallback(async () => {
    try {
      const usage = await window.api.gemini.getDailyUsage()
      setGeminiUsage(usage)
    } catch {
      // silently ignore — usage bar is non-critical
    }
  }, [])

  // Refresh usage on mount
  useEffect(() => {
    refreshUsage()
  }, [refreshUsage])

  // Refresh usage when pipeline finishes (isRunning transitions to false)
  // This picks up the final persisted count from the electron-store
  const prevRunningRef = useRef(isRunning)
  useEffect(() => {
    if (prevRunningRef.current && !isRunning) {
      refreshUsage()
    }
    prevRunningRef.current = isRunning
  }, [isRunning, refreshUsage])

  // During a run, display the committed baseline + live in-progress calls directly
  // from React state — no IPC round-trip needed for the live bar
  const displayUsed = (geminiUsage?.used ?? 0) + (isRunning ? (stats.gemini_api_calls ?? 0) : 0)

  useEffect(() => {
    if (result?.local_path && !result.error) {
      const params = new URLSearchParams({ path: result.local_path })
      if (result.excel_path) params.set('excel', result.excel_path)
      if (result.metadata_path) params.set('meta', result.metadata_path)
      if (result.json_path) params.set('json', result.json_path)
      if (result.warning) params.set('warning', result.warning)
      // F10b: surface strict-gate drops to the Results banner
      const dropPath = result.drop_debug_path || result.debug_path
      if (dropPath) params.set('dropDebug', dropPath)
      const dropCount = stats.strict_gate_drops_count
      if (typeof dropCount === 'number' && dropCount > 0) {
        params.set('dropCount', String(dropCount))
      }
      navigate(`/results?${params.toString()}`)
    }
  }, [result, navigate, stats])

  useEffect(() => {
    if (userLogRef.current) {
      userLogRef.current.scrollTop = userLogRef.current.scrollHeight
    }
  }, [structuredLogs])

  useEffect(() => {
    if (techLogRef.current) {
      techLogRef.current.scrollTop = techLogRef.current.scrollHeight
    }
  }, [logs])

  const statItems = [
    { label: 'Papers found', value: stats.papers_found, color: 'text-blue-600', icon: FileText },
    { label: 'Screened', value: stats.papers_screened, color: 'text-amber-600', icon: Filter },
    { label: 'Analyzed', value: stats.papers_analyzed, color: 'text-violet-600', icon: FlaskConical },
    { label: 'Genes extracted', value: stats.genes_extracted, color: 'text-emerald-600', icon: Dna },
  ]

  // User-facing logs: info, warn, error only
  const userLogs = structuredLogs.filter(
    (l) => l.level === 'info' || l.level === 'warn' || l.level === 'error'
  )

  return (
    <div className="h-full flex flex-col p-6 gap-5 overflow-hidden">
      {/* Header row */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Pipeline</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {isRunning ? (
              <span className="inline-flex items-center gap-2">
                Processing your query...
                <span className="inline-flex items-center gap-1 text-brand-600 font-mono text-xs bg-brand-50 px-2 py-0.5 rounded-full">
                  <Clock className="w-3 h-3" />
                  {formatElapsed(elapsedSeconds)}
                </span>
              </span>
            ) : error ? (
              'Pipeline encountered an error'
            ) : (
              'Pipeline idle'
            )}
          </p>
        </div>
        <div className="flex gap-3">
          {isRunning && (
            <button
              onClick={cancel}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-red-200 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
            >
              <Square className="w-3.5 h-3.5" />
              Cancel
            </button>
          )}
          {!isRunning && error && (
            <button
              onClick={() => navigate('/query')}
              className="inline-flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors"
            >
              <ArrowRight className="w-3.5 h-3.5" />
              Back to Query
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 text-red-600 text-sm flex-shrink-0">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3 flex-shrink-0">
        {statItems.map((item) => {
          const Icon = item.icon
          return (
            <div
              key={item.label}
              className="bg-white rounded-xl shadow-sm border border-slate-100 px-4 py-3 hover:shadow-md hover:border-slate-200 transition-all duration-200"
            >
              <div className="flex items-center gap-1.5">
                <Icon className="w-3.5 h-3.5 text-slate-400" />
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
                  {item.label}
                </p>
              </div>
              <p className={`text-2xl font-bold mt-1 ${item.color}`}>{item.value ?? 0}</p>
            </div>
          )
        })}
      </div>

      {/* Gemini API usage bar */}
      {geminiUsage && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-100 px-4 py-3 flex-shrink-0">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-medium text-slate-400">
              Gemini API usage today (this app only)
            </span>
            <span className="text-xs text-slate-400">Resets at midnight</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  displayUsed / geminiUsage.limit > 0.95
                    ? 'bg-red-500'
                    : displayUsed / geminiUsage.limit > 0.8
                      ? 'bg-amber-500'
                      : 'bg-brand-500'
                }`}
                style={{ width: `${Math.min(100, (displayUsed / geminiUsage.limit) * 100)}%` }}
              />
            </div>
            <span className="text-xs font-medium text-slate-500 tabular-nums flex-shrink-0">
              {displayUsed.toLocaleString()} / {geminiUsage.limit.toLocaleString()} requests
            </span>
          </div>
        </div>
      )}

      {/* Main content: steps + log panels side by side, filling remaining space */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Pipeline steps */}
        <div className="w-56 flex-shrink-0 bg-white rounded-xl shadow-sm border border-slate-100 p-5">
          <PipelineSteps stage={stage} percent={percent} isRunning={isRunning} />
        </div>

        {/* Log panels container */}
        <div className="flex-1 flex flex-col gap-3 min-h-0">
          {/* User-facing log panel */}
          <div
            className={`bg-white rounded-xl shadow-sm border border-slate-100 flex flex-col min-h-0 overflow-hidden ${showTechnical ? 'flex-1' : 'flex-1'}`}
          >
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-100 flex-shrink-0">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Activity Log
              </span>
              <span className="text-xs text-slate-400">{userLogs.length} events</span>
            </div>
            <div
              ref={userLogRef}
              className="flex-1 overflow-y-auto p-4 text-sm leading-relaxed"
            >
              {userLogs.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center py-12">
                  <Beaker className="w-12 h-12 text-slate-200 mb-4" />
                  <p className="text-slate-500 font-medium">No activity yet</p>
                  <p className="text-slate-400 text-sm mt-1">
                    {isRunning ? (
                      'Waiting for pipeline output...'
                    ) : (
                      <>
                        Start a new query to begin analysis.{' '}
                        <button
                          onClick={() => navigate('/query')}
                          className="text-brand-600 hover:text-brand-700 underline underline-offset-2"
                        >
                          Go to Query
                        </button>
                      </>
                    )}
                  </p>
                </div>
              ) : (
                userLogs.map((entry: StructuredLog, i: number) => (
                  <div
                    key={i}
                    className={`flex items-start py-1 pl-3 border-l-2 ${
                      entry.level === 'error'
                        ? 'border-red-400 bg-red-50/50'
                        : entry.level === 'warn'
                          ? 'border-amber-400 bg-amber-50/30'
                          : 'border-slate-200'
                    }`}
                  >
                    <LogLevelIcon level={entry.level} />
                    <span className="text-slate-400 text-xs mr-3 mt-0.5 flex-shrink-0 font-mono tabular-nums">
                      {formatTime(entry.timestamp)}
                    </span>
                    <span
                      className={
                        entry.level === 'error'
                          ? 'text-red-600 font-medium'
                          : entry.level === 'warn'
                            ? 'text-amber-600'
                            : 'text-slate-700'
                      }
                    >
                      {entry.msg}
                    </span>
                    {entry.detail && (
                      <span className="text-slate-400 text-xs ml-2 mt-0.5">{entry.detail}</span>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Technical log panel — collapsible */}
          <div className="flex-shrink-0">
            <button
              onClick={() => setShowTechnical(!showTechnical)}
              className="flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-slate-600 transition-colors py-1"
            >
              {showTechnical ? (
                <ChevronDown className="w-3.5 h-3.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5" />
              )}
              Show technical logs
              <span className="text-slate-300 ml-1">({logs.length} lines)</span>
            </button>
          </div>
          {showTechnical && (
            <div className="bg-slate-900 rounded-xl shadow-sm flex flex-col min-h-0 overflow-hidden flex-1">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700/50 flex-shrink-0">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                  Technical Log
                </span>
                <span className="text-xs text-slate-500">{logs.length} lines</span>
              </div>
              <div
                ref={techLogRef}
                className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed"
              >
                {logs.length === 0 ? (
                  <p className="text-slate-500">Waiting for output...</p>
                ) : (
                  logs.map((line, i) => (
                    <div
                      key={i}
                      className={
                        (line.startsWith('LOG:') && line.includes('"level":"error"'))
                          ? 'text-red-400'
                          : (line.startsWith('LOG:') && line.includes('"level":"warn"'))
                            ? 'text-amber-400'
                            : line.startsWith('PROGRESS:') || line.startsWith('RESULT:')
                              ? 'text-blue-400'
                              : 'text-slate-300'
                      }
                    >
                      {line}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
