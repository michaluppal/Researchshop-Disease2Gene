import { useState } from 'react'
import {
  X,
  ExternalLink,
  AlertTriangle,
  Loader2,
  Trash2,
  ArrowLeft,
  CheckCircle2,
  Search,
} from 'lucide-react'

interface PaperItem {
  title?: string
  pmid?: string
  doi?: string
  pmc?: string
  url: string
  original: string
}

interface SmartInputProps {
  onPapersChange: (pmids: string[], papers: PaperItem[]) => void
}

// Parse various PubMed identifiers from raw text
function parseIdentifiers(text: string): Array<{ type: string; value: string; original: string }> {
  const lines = text
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean)
  const results: Array<{ type: string; value: string; original: string }> = []

  for (const line of lines) {
    // PMID: prefix
    const pmidPrefix = line.match(/^PMID:\s*(\d+)/i)
    if (pmidPrefix) {
      results.push({ type: 'pmid', value: pmidPrefix[1], original: line })
      continue
    }

    // DOI: prefix
    const doiPrefix = line.match(/^DOI:\s*(10\.\S+)/i)
    if (doiPrefix) {
      results.push({ type: 'doi', value: doiPrefix[1], original: line })
      continue
    }

    // PubMed URL
    const pubmedUrl = line.match(/pubmed\.ncbi\.nlm\.nih\.gov\/(\d+)/i)
    if (pubmedUrl) {
      results.push({ type: 'pmid', value: pubmedUrl[1], original: line })
      continue
    }

    // PMC URL
    const pmcUrl = line.match(/ncbi\.nlm\.nih\.gov\/pmc\/articles\/PMC(\d+)/i)
    if (pmcUrl) {
      results.push({ type: 'pmc', value: `PMC${pmcUrl[1]}`, original: line })
      continue
    }

    // DOI URL
    const doiUrl = line.match(/doi\.org\/(10\.\S+)/i)
    if (doiUrl) {
      results.push({ type: 'doi', value: doiUrl[1], original: line })
      continue
    }

    // PMC ID
    const pmcId = line.match(/^PMC\d+$/i)
    if (pmcId) {
      results.push({ type: 'pmc', value: line.toUpperCase(), original: line })
      continue
    }

    // Raw DOI
    const rawDoi = line.match(/^10\.\d{4,}\/\S+/)
    if (rawDoi) {
      results.push({ type: 'doi', value: rawDoi[0], original: line })
      continue
    }

    // Raw PMID (just digits)
    if (/^\d{1,8}$/.test(line)) {
      results.push({ type: 'pmid', value: line, original: line })
      continue
    }

    results.push({ type: 'unknown', value: line, original: line })
  }

  return results
}

export default function SmartInput({ onPapersChange }: SmartInputProps) {
  const [text, setText] = useState('')
  const [mode, setMode] = useState<'edit' | 'validated'>('edit')
  const [papers, setPapers] = useState<PaperItem[]>([])
  const [invalid, setInvalid] = useState<string[]>([])
  const [validating, setValidating] = useState(false)

  const detectedCount = text.trim()
    ? text
        .split(/[\n,;]+/)
        .map((s) => s.trim())
        .filter(Boolean).length
    : 0

  const validate = async () => {
    setValidating(true)
    setInvalid([])

    const parsed = parseIdentifiers(text)
    const pmidItems = parsed.filter((p) => p.type === 'pmid')
    const unknowns = parsed.filter((p) => p.type === 'unknown')
    const doiItems = parsed.filter((p) => p.type === 'doi')
    const pmcItems = parsed.filter((p) => p.type === 'pmc')

    setInvalid(unknowns.map((u) => u.original))

    // Collect all PMIDs to fetch
    const pmids = pmidItems.map((p) => p.value)

    try {
      const details = pmids.length > 0 ? await window.api.pubmed.fetchDetails(pmids) : {}

      const validPapers: PaperItem[] = []

      for (const item of pmidItems) {
        const d = details[item.value]
        validPapers.push({
          pmid: item.value,
          title: d?.title,
          doi: d?.doi,
          pmc: d?.pmc,
          url: d?.url || `https://pubmed.ncbi.nlm.nih.gov/${item.value}/`,
          original: item.original,
        })
      }

      // DOI items (no enrichment yet, just store them)
      for (const item of doiItems) {
        validPapers.push({
          doi: item.value,
          url: `https://doi.org/${item.value}`,
          original: item.original,
        })
      }

      // PMC items
      for (const item of pmcItems) {
        validPapers.push({
          pmc: item.value,
          url: `https://www.ncbi.nlm.nih.gov/pmc/articles/${item.value}/`,
          original: item.original,
        })
      }

      setPapers(validPapers)
      setMode('validated')
    } catch {
      setInvalid((prev) => [...prev, 'Failed to validate some identifiers'])
    } finally {
      setValidating(false)
    }
  }

  const removePaper = (index: number) => {
    setPapers((prev) => prev.filter((_, i) => i !== index))
  }

  const clearAll = () => {
    setText('')
    setPapers([])
    setInvalid([])
    setMode('edit')
  }

  const backToEdit = () => {
    setMode('edit')
  }

  const useValid = () => {
    const pmids = papers.filter((p) => p.pmid).map((p) => p.pmid!)
    onPapersChange(pmids, papers)
  }

  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1.5">
        Specific Papers (PMIDs, DOIs, URLs)
      </label>

      {mode === 'edit' ? (
        <>
          <div className="relative">
            <div className="absolute left-3 top-2.5 text-slate-400 pointer-events-none">
              {validating ? (
                <Loader2 className="w-4 h-4 animate-spin text-brand-500" />
              ) : (
                <Search className="w-4 h-4" />
              )}
            </div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={`Paste PMIDs, DOIs, PMC IDs, or PubMed URLs\nSeparate by commas, newlines, or semicolons\n\nExamples:\n  12345678\n  PMID: 12345678\n  DOI: 10.1234/example\n  https://pubmed.ncbi.nlm.nih.gov/12345678/`}
              rows={6}
              className="w-full rounded-lg border border-gray-300 pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 resize-none font-mono transition-shadow"
            />
            {detectedCount > 0 && (
              <span className="absolute top-2 right-2 inline-flex items-center px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 text-xs font-medium">
                {detectedCount} item{detectedCount !== 1 ? 's' : ''} detected
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 mt-2">
            <button
              onClick={validate}
              disabled={!text.trim() || validating}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {validating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Validating...
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  Validate
                </>
              )}
            </button>
          </div>
        </>
      ) : (
        <>
          {/* Validated papers table */}
          {papers.length > 0 && (
            <div className="border border-slate-200 rounded-lg shadow-lg overflow-hidden animate-fade-in-slide">
              <div className="max-h-72 overflow-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10">
                    <tr>
                      <th className="text-left px-4 py-2 text-xs font-medium text-slate-500">Paper</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-slate-500 w-28">ID</th>
                      <th className="w-16"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {papers.map((paper, i) => (
                      <tr key={i} className="hover:bg-brand-50 transition-colors group">
                        <td className="px-4 py-2.5">
                          <p className="font-medium text-slate-900 group-hover:text-brand-600 line-clamp-1 transition-colors">
                            {paper.title || paper.original}
                          </p>
                          {paper.doi && (
                            <span className="text-xs text-slate-400">DOI: {paper.doi}</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          {paper.pmid && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-xs font-mono">
                              {paper.pmid}
                            </span>
                          )}
                          {!paper.pmid && paper.pmc && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-green-50 text-green-700 text-xs font-mono">
                              {paper.pmc}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => window.api.shell.openExternal(paper.url)}
                              className="p-1 text-slate-400 hover:text-brand-600 transition-colors"
                              title="View Source"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => removePaper(i)}
                              className="p-1 text-slate-400 hover:text-red-500 transition-colors"
                              title="Remove"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Invalid items */}
          {invalid.length > 0 && (
            <div className="mt-3 p-3 rounded-lg bg-amber-50 border border-amber-200 animate-fade-in-slide">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                <span className="text-sm font-medium text-amber-800">
                  {invalid.length} invalid item{invalid.length !== 1 ? 's' : ''}
                </span>
              </div>
              <p className="text-xs text-amber-600">
                {invalid.join(', ')}
              </p>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={backToEdit}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-600 rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Edit
            </button>
            <button
              onClick={clearAll}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-600 rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Clear All
            </button>
            {papers.length > 0 && (
              <button
                onClick={useValid}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 transition-colors"
              >
                <CheckCircle2 className="w-4 h-4" />
                Use {papers.length} Valid Item{papers.length !== 1 ? 's' : ''}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}
