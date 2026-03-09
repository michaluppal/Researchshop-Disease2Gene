import { useState } from 'react'
import { Play, Search, Users, FileText, Zap } from 'lucide-react'

interface ProtocolConfig {
  topic: boolean
  papers: boolean
  authors: boolean
}

interface StartScreenProps {
  onStartProtocol: (config: ProtocolConfig, name: string) => void
}

const PREBUILT_PROTOCOLS = [
  {
    name: 'Full Protocol',
    description: 'Comprehensive search combining topic keywords, specific papers, and author names for maximum coverage',
    icon: Zap,
    config: { topic: true, papers: true, authors: true },
    color: 'brand',
  },
  {
    name: 'Author Discovery',
    description: 'Find and analyze all publications from specific researchers across PubMed',
    icon: Users,
    config: { topic: false, papers: false, authors: true },
    color: 'emerald',
  },
  {
    name: 'Paper Analysis',
    description: 'Extract gene and variant data from known papers using PMIDs, DOIs, or PubMed URLs',
    icon: FileText,
    config: { topic: false, papers: true, authors: false },
    color: 'violet',
  },
  {
    name: 'Hybrid',
    description: 'Combine an author search with specific paper IDs to cover a targeted set of literature',
    icon: Search,
    config: { topic: false, papers: true, authors: true },
    color: 'amber',
  },
] as const

const COLOR_MAP: Record<string, { bg: string; border: string; topBorder: string; text: string; icon: string }> = {
  brand: {
    bg: 'bg-brand-50 hover:bg-brand-100',
    border: 'border-brand-200',
    topBorder: 'border-t-brand-500',
    text: 'text-brand-700',
    icon: 'text-brand-600',
  },
  emerald: {
    bg: 'bg-emerald-50 hover:bg-emerald-100',
    border: 'border-emerald-200',
    topBorder: 'border-t-emerald-500',
    text: 'text-emerald-700',
    icon: 'text-emerald-600',
  },
  violet: {
    bg: 'bg-violet-50 hover:bg-violet-100',
    border: 'border-violet-200',
    topBorder: 'border-t-violet-500',
    text: 'text-violet-700',
    icon: 'text-violet-600',
  },
  amber: {
    bg: 'bg-amber-50 hover:bg-amber-100',
    border: 'border-amber-200',
    topBorder: 'border-t-amber-500',
    text: 'text-amber-700',
    icon: 'text-amber-600',
  },
}

const TOGGLE_CARDS = [
  { key: 'topic' as const, label: 'Topic Search', description: 'Search PubMed by keywords and MeSH terms', icon: Search },
  { key: 'papers' as const, label: 'Specific Papers', description: 'Enter PMIDs, DOIs, or PubMed URLs directly', icon: FileText },
  { key: 'authors' as const, label: 'Authors', description: 'Find papers by researcher name', icon: Users },
]

export default function StartScreen({ onStartProtocol }: StartScreenProps) {
  const [custom, setCustom] = useState<ProtocolConfig>({ topic: false, papers: false, authors: false })
  const [showCustom, setShowCustom] = useState(false)

  const anySelected = custom.topic || custom.papers || custom.authors

  const getCustomName = () => {
    const parts: string[] = []
    if (custom.topic) parts.push('Topic')
    if (custom.papers) parts.push('Papers')
    if (custom.authors) parts.push('Authors')
    return parts.length ? `Custom (${parts.join(' + ')})` : 'Custom Protocol'
  }

  return (
    <div className="flex items-center justify-center min-h-full p-8">
      <div className="max-w-2xl w-full">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-slate-900 mb-2">Begin Research Protocol</h1>
          <p className="text-slate-500">Choose how you want to find and analyze biomedical papers</p>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-8">
          {PREBUILT_PROTOCOLS.map((proto) => {
            const colors = COLOR_MAP[proto.color]
            const Icon = proto.icon
            return (
              <button
                key={proto.name}
                onClick={() => onStartProtocol(proto.config, proto.name)}
                className={`${colors.bg} ${colors.border} ${colors.topBorder} border border-t-2 rounded-xl p-5 text-left transition-all duration-200 hover:shadow-lg hover:scale-[1.02]`}
              >
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${colors.bg} mb-3`}>
                  <Icon className={`w-5 h-5 ${colors.icon}`} />
                </div>
                <h3 className={`font-bold ${colors.text} mb-1`}>{proto.name}</h3>
                <p className="text-sm text-slate-500 leading-snug">{proto.description}</p>
              </button>
            )
          })}
        </div>

        <div className="border-t border-slate-200 pt-8 mt-2">
          <button
            onClick={() => setShowCustom(!showCustom)}
            className="text-sm font-medium text-slate-500 hover:text-slate-800 transition-colors mb-5"
          >
            {showCustom ? 'Hide custom builder' : 'Or build a custom protocol...'}
          </button>

          {showCustom && (
            <div className="space-y-3">
              {TOGGLE_CARDS.map((card) => {
                const Icon = card.icon
                const active = custom[card.key]
                return (
                  <button
                    key={card.key}
                    onClick={() => setCustom((prev) => ({ ...prev, [card.key]: !prev[card.key] }))}
                    className={`w-full flex items-center gap-4 p-4 rounded-xl border transition-all ${
                      active
                        ? 'border-brand-300 bg-brand-50'
                        : 'border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <Icon className={`w-5 h-5 ${active ? 'text-brand-600' : 'text-slate-400'}`} />
                    <div className="flex-1 text-left">
                      <div className={`font-medium text-sm ${active ? 'text-brand-700' : 'text-slate-700'}`}>
                        {card.label}
                      </div>
                      <div className="text-xs text-slate-500">{card.description}</div>
                    </div>
                    <div
                      className={`relative w-10 h-6 rounded-full transition-colors duration-200 flex-shrink-0 ${
                        active ? 'bg-brand-600' : 'bg-slate-300'
                      }`}
                    >
                      <div
                        className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${
                          active ? 'translate-x-5' : 'translate-x-1'
                        }`}
                      />
                    </div>
                  </button>
                )
              })}

              <button
                onClick={() => onStartProtocol(custom, getCustomName())}
                disabled={!anySelected}
                className="w-full mt-4 inline-flex items-center justify-center gap-2 px-6 py-3 bg-brand-600 text-white rounded-xl font-medium hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Play className="w-4 h-4" />
                Initialize Protocol
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
