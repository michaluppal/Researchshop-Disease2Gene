import { useState, useMemo, Fragment } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Trash2,
  ExternalLink,
  Clock,
  AlertCircle,
  Search,
  ChevronDown,
  ChevronUp,
  Archive,
  CheckCircle,
  XCircle,
  Activity,
} from 'lucide-react'
import { useJobHistory, Job } from '../hooks/useJobHistory'

const statusConfig: Record<
  string,
  { label: string; className: string; icon: typeof CheckCircle | null }
> = {
  completed: {
    label: 'Completed',
    className: 'bg-green-100 text-green-700',
    icon: CheckCircle,
  },
  failed: {
    label: 'Failed',
    className: 'bg-red-100 text-red-700',
    icon: XCircle,
  },
  running: {
    label: 'Running',
    className: 'bg-yellow-100 text-yellow-700',
    icon: null,
  },
  cancelled: {
    label: 'Cancelled',
    className: 'bg-slate-100 text-slate-600',
    icon: null,
  },
  queued: {
    label: 'Queued',
    className: 'bg-blue-100 text-blue-700',
    icon: null,
  },
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now()
  const date = new Date(dateStr).getTime()
  const diffMs = now - date
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHr = Math.floor(diffMin / 60)
  const diffDays = Math.floor(diffHr / 24)

  if (diffSec < 60) return 'Just now'
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`
  if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? '' : 's'} ago`
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 30) return `${diffDays} days ago`
  const diffMonths = Math.floor(diffDays / 30)
  if (diffMonths < 12) return `${diffMonths} month${diffMonths === 1 ? '' : 's'} ago`
  const diffYears = Math.floor(diffDays / 365)
  return `${diffYears} year${diffYears === 1 ? '' : 's'} ago`
}

function parseStats(statsStr: string | null): Record<string, unknown> | null {
  if (!statsStr) return null
  try {
    return JSON.parse(statsStr)
  } catch {
    return null
  }
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return '--'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (ms < 0) return '--'
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  const remSec = sec % 60
  return `${min}m ${remSec}s`
}

function ExpandedDetails({ job }: { job: Job }) {
  const stats = parseStats(job.stats)
  return (
    <div className="px-4 py-3 bg-slate-50/80 border-b border-slate-100 text-sm text-slate-600">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <span className="text-slate-400 text-xs block">Duration</span>
          {formatDuration(job.created_at, job.completed_at)}
        </div>
        <div>
          <span className="text-slate-400 text-xs block">Papers analyzed</span>
          {stats?.papers_analyzed != null ? String(stats.papers_analyzed) : '--'}
        </div>
        <div>
          <span className="text-slate-400 text-xs block">Genes found</span>
          {stats?.genes_extracted != null ? String(stats.genes_extracted) : '--'}
        </div>
        <div>
          <span className="text-slate-400 text-xs block">API calls</span>
          {stats?.gemini_api_calls != null ? String(stats.gemini_api_calls) : '--'}
        </div>
      </div>
      {job.columns && (
        <div className="mt-2">
          <span className="text-slate-400 text-xs block">Columns</span>
          <span className="text-xs">{job.columns}</span>
        </div>
      )}
      {job.error && (
        <div className="mt-2">
          <span className="text-red-400 text-xs block">Error</span>
          <span className="text-xs text-red-600">{job.error}</span>
        </div>
      )}
    </div>
  )
}

export default function History() {
  const navigate = useNavigate()
  const { jobs, loading, deleteJob } = useJobHistory()
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const filteredJobs = useMemo(() => {
    if (!searchQuery.trim()) return jobs
    const q = searchQuery.toLowerCase()
    return jobs.filter(
      (job) =>
        (job.query && job.query.toLowerCase().includes(q)) ||
        (job.status && job.status.toLowerCase().includes(q))
    )
  }, [jobs, searchQuery])

  const handleDelete = async (id: string) => {
    if (confirmDelete === id) {
      await deleteJob(id)
      setConfirmDelete(null)
      if (expandedId === id) setExpandedId(null)
    } else {
      setConfirmDelete(id)
    }
  }

  const openResult = (job: Job) => {
    if (!job.result_path) return
    const params = new URLSearchParams({ path: job.result_path, jobId: job.id })
    if (job.excel_path) params.set('excel', job.excel_path)
    if (job.metadata_path) params.set('meta', job.metadata_path)
    if (job.json_path) params.set('json', job.json_path)
    if (job.candidate_audit_path) params.set('candidateAudit', job.candidate_audit_path)
    navigate(`/results?${params.toString()}`)
  }

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-brand-600" />
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-2xl font-bold text-slate-900 mb-1">History</h1>
      <p className="text-sm text-slate-500 mb-6">Previous pipeline runs</p>

      {jobs.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm p-16 text-center">
          <Archive className="w-16 h-16 text-slate-200 mx-auto mb-5" strokeWidth={1.5} />
          <h3 className="text-lg font-medium text-slate-600 mb-2">No jobs yet</h3>
          <p className="text-sm text-slate-400 mb-6">
            Run a pipeline from the Query Builder to see results here.
          </p>
          <button
            onClick={() => navigate('/query')}
            className="inline-flex items-center px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 transition-colors"
          >
            Start your first query
          </button>
        </div>
      ) : (
        <>
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Filter by query or status..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            />
          </div>

          {filteredJobs.length === 0 ? (
            <div className="bg-white rounded-xl shadow-sm p-12 text-center">
              <Search className="w-10 h-10 text-slate-200 mx-auto mb-3" />
              <p className="text-sm text-slate-500">No jobs match your search.</p>
            </div>
          ) : (
            <div className="bg-white rounded-xl shadow-sm overflow-hidden">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="w-8 px-2 py-3" />
                    <th className="px-4 py-3 text-left font-medium text-slate-600">Query</th>
                    <th className="px-4 py-3 text-left font-medium text-slate-600">Status</th>
                    <th className="px-4 py-3 text-left font-medium text-slate-600">Date</th>
                    <th className="px-4 py-3 text-right font-medium text-slate-600">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredJobs.map((job) => {
                    const sc = statusConfig[job.status] || statusConfig.cancelled
                    const isExpanded = expandedId === job.id
                    const StatusIcon = sc.icon
                    return (
                      <Fragment key={job.id}>
                        <tr
                          className="border-b border-slate-100 hover:bg-slate-50/50 cursor-pointer"
                          onClick={() => toggleExpand(job.id)}
                        >
                          <td className="pl-3 pr-0 py-3 text-slate-400">
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </td>
                          <td className="px-4 py-3 text-slate-700 max-w-xs truncate">
                            {job.query || '(PMIDs only)'}
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${sc.className}`}
                            >
                              {StatusIcon && <StatusIcon className="w-3 h-3" />}
                              {sc.label}
                            </span>
                          </td>
                          <td
                            className="px-4 py-3 text-slate-500"
                            title={new Date(job.created_at).toLocaleString()}
                          >
                            {formatRelativeTime(job.created_at)}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div
                              className="inline-flex gap-1"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {job.status === 'running' && (
                                <button
                                  onClick={() => navigate('/pipeline')}
                                  className="p-1.5 rounded-lg text-amber-500 hover:text-amber-600 hover:bg-amber-50"
                                  title="View live progress"
                                >
                                  <Activity className="w-4 h-4 animate-pulse" />
                                </button>
                              )}
                              {job.result_path && job.status === 'completed' && (
                                <button
                                  onClick={() => openResult(job)}
                                  className="p-1.5 rounded-lg text-slate-400 hover:text-brand-600 hover:bg-brand-50"
                                  title="View results"
                                >
                                  <ExternalLink className="w-4 h-4" />
                                </button>
                              )}
                              {job.error && (
                                <span title={job.error}>
                                  <AlertCircle className="w-4 h-4 text-red-400 mt-1.5 mx-1" />
                                </span>
                              )}
                              <button
                                onClick={() => handleDelete(job.id)}
                                className={`p-1.5 rounded-lg ${
                                  confirmDelete === job.id
                                    ? 'text-red-600 bg-red-50'
                                    : 'text-slate-400 hover:text-red-500 hover:bg-red-50'
                                }`}
                                title={
                                  confirmDelete === job.id ? 'Click again to confirm' : 'Delete'
                                }
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr>
                            <td colSpan={5} className="p-0">
                              <ExpandedDetails job={job} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
