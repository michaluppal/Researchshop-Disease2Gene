import { useState } from 'react'
import {
  X,
  ExternalLink,
  Loader2,
  Search,
  Users,
  FileText,
  Inbox,
  Rocket,
  AlertTriangle,
} from 'lucide-react'

interface PaperItem {
  title?: string
  pmid?: string
  doi?: string
  pmc?: string
  url: string
  source?: string
}

interface FinalReviewModalProps {
  isOpen: boolean
  onClose: () => void
  topicPapers: PaperItem[]
  authorPapers: PaperItem[]
  specificPapers: PaperItem[]
  onRemoveTopicPaper: (pmid: string) => void
  onRemoveAuthorPaper: (pmid: string) => void
  onRemoveSpecificPaper: (pmid: string) => void
  onRunPipeline: () => void
  loading: boolean
}

type TabKey = 'all' | 'topic' | 'author' | 'specific'

const SOURCE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  topic: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
  author: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
  specific: { bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200' },
}

export default function FinalReviewModal({
  isOpen,
  onClose,
  topicPapers,
  authorPapers,
  specificPapers,
  onRemoveTopicPaper,
  onRemoveAuthorPaper,
  onRemoveSpecificPaper,
  onRunPipeline,
  loading,
}: FinalReviewModalProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('all')

  if (!isOpen) return null

  const allPapers = [
    ...topicPapers.map((p) => ({ ...p, source: 'topic' })),
    ...authorPapers.map((p) => ({ ...p, source: 'author' })),
    ...specificPapers.map((p) => ({ ...p, source: 'specific' })),
  ]

  const totalCount = allPapers.length

  const getTabPapers = (): Array<PaperItem & { source: string }> => {
    switch (activeTab) {
      case 'topic':
        return topicPapers.map((p) => ({ ...p, source: 'topic' }))
      case 'author':
        return authorPapers.map((p) => ({ ...p, source: 'author' }))
      case 'specific':
        return specificPapers.map((p) => ({ ...p, source: 'specific' }))
      default:
        return allPapers
    }
  }

  const getRemoveHandler = (source: string) => {
    switch (source) {
      case 'topic':
        return onRemoveTopicPaper
      case 'author':
        return onRemoveAuthorPaper
      case 'specific':
        return onRemoveSpecificPaper
      default:
        return () => {}
    }
  }

  const papers = getTabPapers()

  const tabs: Array<{ key: TabKey; label: string; count: number; icon: typeof Search; color: string }> = [
    { key: 'all', label: 'All Papers', count: totalCount, icon: Inbox, color: 'slate' },
    { key: 'topic', label: 'Topic Search', count: topicPapers.length, icon: Search, color: 'blue' },
    { key: 'author', label: 'From Authors', count: authorPapers.length, icon: Users, color: 'emerald' },
    { key: 'specific', label: 'Specific IDs', count: specificPapers.length, icon: FileText, color: 'violet' },
  ]

  const tabColors: Record<string, { active: string; inactive: string }> = {
    slate: { active: 'border-slate-900 text-slate-900', inactive: 'border-transparent text-slate-500 hover:text-slate-700' },
    blue: { active: 'border-blue-600 text-blue-600', inactive: 'border-transparent text-slate-500 hover:text-blue-600' },
    emerald: { active: 'border-emerald-600 text-emerald-600', inactive: 'border-transparent text-slate-500 hover:text-emerald-600' },
    violet: { active: 'border-violet-600 text-violet-600', inactive: 'border-transparent text-slate-500 hover:text-violet-600' },
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-50/95 backdrop-blur-sm flex flex-col">
      {/* Sticky header */}
      <div className="flex-shrink-0 bg-white border-b border-slate-200 shadow-sm">
        <div className="flex items-center justify-between px-6 pt-5 pb-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">Review Papers</h2>
            <p className="text-sm text-slate-500 mt-1">
              {totalCount} paper{totalCount !== 1 ? 's' : ''} ready for analysis
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Summary cards */}
        <div className="flex items-center gap-3 px-6 pb-4">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-50 border border-blue-100">
            <Search className="w-4 h-4 text-blue-600" />
            <span className="text-xs font-medium text-blue-700">
              {topicPapers.length} Topic
            </span>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-100">
            <Users className="w-4 h-4 text-emerald-600" />
            <span className="text-xs font-medium text-emerald-700">
              {authorPapers.length} Author
            </span>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-violet-50 border border-violet-100">
            <FileText className="w-4 h-4 text-violet-600" />
            <span className="text-xs font-medium text-violet-700">
              {specificPapers.length} Specific
            </span>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex items-center gap-6 px-6 border-t border-slate-100">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.key
            const colors = tabColors[tab.color]
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`inline-flex items-center gap-1.5 pt-3 pb-3 border-b-2 text-sm font-medium transition-colors ${
                  isActive ? colors.active : colors.inactive
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
                <span
                  className={`ml-1 px-1.5 py-0.5 rounded-full text-xs ${
                    isActive ? 'bg-slate-100 text-slate-700' : 'bg-slate-50 text-slate-400'
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto px-6 py-4">
        {papers.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <Inbox className="w-12 h-12 mb-3" />
            <p className="text-sm font-medium">No papers in this category</p>
          </div>
        ) : (
          <div className="space-y-2">
            {papers.map((paper, i) => {
              const paperId = paper.pmid || paper.doi || paper.pmc || paper.url
              const sourceColor = SOURCE_COLORS[paper.source] || SOURCE_COLORS.specific
              const removeHandler = getRemoveHandler(paper.source)

              return (
                <div
                  key={`${paper.source}-${paperId}-${i}`}
                  className="group flex items-start gap-3 p-4 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-all"
                >
                  {/* Source badge */}
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 mt-0.5 ${sourceColor.bg} ${sourceColor.text}`}
                  >
                    {paper.source === 'topic' ? 'Topic' : paper.source === 'author' ? 'Author' : 'ID'}
                  </span>

                  <div className="flex-1 min-w-0">
                    {/* IDs */}
                    <div className="flex items-center gap-2 mb-1">
                      {paper.pmid && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-xs font-mono">
                          PMID: {paper.pmid}
                        </span>
                      )}
                      {paper.doi && <span className="text-xs text-slate-400">DOI: {paper.doi}</span>}
                    </div>

                    {/* Title */}
                    <p className="text-sm font-semibold text-slate-900 line-clamp-2">
                      {paper.title || 'Untitled'}
                    </p>

                    {/* View source */}
                    <button
                      onClick={() => window.api.shell.openExternal(paper.url)}
                      className="inline-flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 mt-1 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" />
                      View Source
                    </button>
                  </div>

                  {/* Remove button */}
                  <button
                    onClick={() => removeHandler(paperId)}
                    className="p-1.5 text-slate-300 hover:text-red-500 rounded-lg hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all flex-shrink-0"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Sticky footer */}
      <div className="flex-shrink-0 border-t border-slate-200 bg-white">
        {totalCount > 0 && (
          <div className="flex items-start gap-2 px-6 pt-3 pb-0">
            <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700">
              Analysis uses your Gemini API quota. Each paper requires multiple API calls.
            </p>
          </div>
        )}
        <div className="flex items-center justify-between px-6 py-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-700 rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
          >
            Continue Editing
          </button>
          <button
            onClick={onRunPipeline}
            disabled={totalCount === 0 || loading}
            className="inline-flex items-center gap-2 px-7 py-2.5 text-sm font-semibold text-white bg-brand-600 rounded-xl hover:bg-brand-700 shadow-md hover:shadow-lg disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none transition-all"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Starting...
              </>
            ) : (
              <>
                <Rocket className="w-4 h-4" />
                Run Analysis ({totalCount})
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
