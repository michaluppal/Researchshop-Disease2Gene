import { createContext, createElement, useCallback, useContext, useEffect, useState, ReactNode } from 'react'

export interface StructuredLog {
  level: string
  msg: string
  detail: string | null
  timestamp: string
}

interface PipelineState {
  stage: string
  percent: number
  // stats contains numeric counters plus, at run-completion, a list of strict-gate drops
  // (field `strict_gate_drops`). The drops list is ignored by the progress UI — the count
  // is exposed separately via `strict_gate_drops_count` (number).
  stats: Record<string, number>
  result: { local_path?: string; metadata_path?: string; excel_path?: string; json_path?: string; debug_path?: string; drop_debug_path?: string; warning?: string; error?: string } | null
  isRunning: boolean
  error: string | null
  logs: string[]
  structuredLogs: StructuredLog[]
}

interface PipelineContextValue extends PipelineState {
  start: (args: Parameters<typeof window.api.pipeline.start>[0]) => ReturnType<typeof window.api.pipeline.start>
  cancel: () => ReturnType<typeof window.api.pipeline.cancel>
}

const PipelineContext = createContext<PipelineContextValue | null>(null)

export function PipelineProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PipelineState>({
    stage: '',
    percent: 0,
    stats: {},
    result: null,
    isRunning: false,
    error: null,
    logs: [],
    structuredLogs: [],
  })

  useEffect(() => {
    const unsubs = [
      window.api.pipeline.onProgress((data) => {
        setState((s) => ({
          ...s,
          stage: data.stage,
          percent: data.percent,
          stats: data.stats,
          isRunning: true,
        }))
      }),
      window.api.pipeline.onResult((data) => {
        setState((s) => ({
          ...s,
          result: data,
          isRunning: false,
          error: data.error || null,
        }))
      }),
      window.api.pipeline.onLog((text) => {
        setState((s) => ({ ...s, logs: [...s.logs.slice(-500), text] }))
      }),
      window.api.pipeline.onStructuredLog((data) => {
        const entry: StructuredLog = {
          level: data.level,
          msg: data.msg,
          detail: data.detail,
          timestamp: data.timestamp,
        }
        setState((s) => ({
          ...s,
          structuredLogs: [...s.structuredLogs.slice(-200), entry],
        }))
      }),
      window.api.pipeline.onExit(() => {
        setState((s) => ({ ...s, isRunning: false }))
      }),
      window.api.pipeline.onError(({ message }) => {
        setState((s) => ({ ...s, error: message, isRunning: false }))
      }),
    ]
    return () => unsubs.forEach((u) => u())
  }, [])

  const start = useCallback(
    async (args: Parameters<typeof window.api.pipeline.start>[0]) => {
      setState((s) => ({
        ...s,
        isRunning: true,
        error: null,
        result: null,
        stage: 'Starting...',
        percent: 0,
        stats: {},
        logs: [],
        structuredLogs: [],
      }))
      return window.api.pipeline.start(args)
    },
    []
  )

  const cancel = useCallback(() => window.api.pipeline.cancel(), [])

  return createElement(PipelineContext.Provider, { value: { ...state, start, cancel } }, children)
}

export function usePipeline(): PipelineContextValue {
  const ctx = useContext(PipelineContext)
  if (!ctx) throw new Error('usePipeline must be used within PipelineProvider')
  return ctx
}
