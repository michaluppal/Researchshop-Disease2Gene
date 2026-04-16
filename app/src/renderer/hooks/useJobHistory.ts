import { useState, useEffect, useCallback } from 'react'

export interface Job {
  id: string
  query: string
  columns: string
  status: string
  created_at: string
  completed_at: string | null
  result_path: string | null
  metadata_path: string | null
  excel_path: string | null
  json_path: string | null
  stats: string | null
  error: string | null
}

export function useJobHistory() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const list = await window.api.history.list()
    setJobs(list)
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const deleteJob = async (id: string) => {
    await window.api.history.delete(id)
    await refresh()
  }

  return { jobs, loading, refresh, deleteJob }
}
