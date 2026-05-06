import { useState, useEffect, useMemo } from 'react'
import {
  Key,
  Mail,
  Folder,
  Zap,
  Check,
  Loader2,
  Eye,
  EyeOff,
  ExternalLink,
  AlertCircle,
  Info,
  Shield
} from 'lucide-react'
import { useSettings } from '../hooks/useSettings'

export default function Settings() {
  const { settings, loading, updateSetting } = useSettings()
  const [geminiKey, setGeminiKey] = useState('')
  const [entrezEmail, setEntrezEmail] = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [parallelAnalysis, setParallelAnalysis] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [version, setVersion] = useState('')
  const [validating, setValidating] = useState(false)
  const [keyStatus, setKeyStatus] = useState<'idle' | 'valid' | 'invalid'>('idle')
  const [keyError, setKeyError] = useState('')

  useEffect(() => {
    if (settings) {
      setGeminiKey(settings.geminiApiKey)
      setEntrezEmail(settings.entrezEmail)
      setOutputDir(settings.outputDirectory)
      setParallelAnalysis(settings.parallelAnalysis)
    }
  }, [settings])

  useEffect(() => {
    window.api.app.version().then(setVersion)
  }, [])

  const isDirty = useMemo(() => {
    if (!settings) return false
    return (
      geminiKey !== settings.geminiApiKey ||
      entrezEmail !== settings.entrezEmail ||
      outputDir !== settings.outputDirectory ||
      parallelAnalysis !== settings.parallelAnalysis
    )
  }, [settings, geminiKey, entrezEmail, outputDir, parallelAnalysis])

  const validateKey = async () => {
    if (!geminiKey.trim()) return
    setValidating(true)
    setKeyStatus('idle')
    setKeyError('')
    try {
      const result = await window.api.settings.validateGeminiKey(geminiKey)
      if (result.valid) {
        setKeyStatus('valid')
      } else {
        setKeyStatus('invalid')
        setKeyError(result.error || 'Invalid API key')
      }
    } catch {
      setKeyStatus('invalid')
      setKeyError('Connection error')
    }
    setValidating(false)
  }

  const browse = async () => {
    const result = (await window.api.dialog.openDirectory()) as {
      canceled: boolean
      filePaths: string[]
    }
    if (!result.canceled && result.filePaths[0]) {
      setOutputDir(result.filePaths[0])
    }
  }

  const save = async () => {
    setSaving(true)
    await updateSetting('geminiApiKey', geminiKey)
    await updateSetting('entrezEmail', entrezEmail)
    await updateSetting('outputDirectory', outputDir)
    await updateSetting('parallelAnalysis', parallelAnalysis)
    setSaving(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-brand-600" />
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Settings</h1>

      {/* API Configuration */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
          <Key className="w-4 h-4" />
          API Configuration
        </h2>

        <div className="space-y-4">
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-slate-700 mb-1.5">
              <Shield className="w-4 h-4 text-slate-400" />
              Gemini API Key
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={geminiKey}
                  onChange={(e) => {
                    setGeminiKey(e.target.value)
                    setKeyStatus('idle')
                    setKeyError('')
                  }}
                  placeholder="Enter your Google Gemini API key"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm pr-10 outline-none transition-shadow focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
                />
                <button
                  type="button"
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 transition-colors"
                >
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <button
                onClick={validateKey}
                disabled={validating || !geminiKey.trim()}
                className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border transition-colors whitespace-nowrap ${
                  keyStatus === 'valid'
                    ? 'border-green-300 bg-green-50 text-green-700'
                    : keyStatus === 'invalid'
                      ? 'border-red-300 bg-red-50 text-red-700'
                      : 'border-slate-300 hover:bg-slate-50 text-slate-700'
                } disabled:opacity-50`}
              >
                {validating ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : keyStatus === 'valid' ? (
                  <Check className="w-3.5 h-3.5" />
                ) : keyStatus === 'invalid' ? (
                  <AlertCircle className="w-3.5 h-3.5" />
                ) : null}
                {keyStatus === 'valid' ? 'Valid' : keyStatus === 'invalid' ? 'Invalid' : 'Validate'}
              </button>
            </div>
            {keyStatus === 'invalid' && keyError && (
              <p className="mt-1.5 text-xs text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3 h-3 flex-shrink-0" />
                {keyError}
              </p>
            )}
            {keyStatus === 'valid' && (
              <p className="mt-1.5 text-xs text-green-600 flex items-center gap-1">
                <Check className="w-3 h-3 flex-shrink-0" />
                API key is valid and connected
              </p>
            )}
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-slate-700 mb-1.5">
              <Mail className="w-4 h-4 text-slate-400" />
              NCBI / Entrez Email
            </label>
            <input
              type="email"
              value={entrezEmail}
              onChange={(e) => setEntrezEmail(e.target.value)}
              placeholder="your@email.com"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none transition-shadow focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
            />
            <p className="mt-1 text-xs text-slate-400">
              Required by NCBI for PubMed API access
            </p>
          </div>
        </div>
      </div>

      {/* Output Settings */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
          <Folder className="w-4 h-4" />
          Output Settings
        </h2>
        <label className="block text-sm font-medium text-slate-700 mb-1.5">Output Directory</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={outputDir}
            readOnly
            className="flex-1 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-600 outline-none cursor-default"
          />
          <button
            onClick={browse}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
          >
            Browse
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-400">Where pipeline results (CSV, metadata) are saved</p>
      </div>

      {/* Performance */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
          <Zap className="w-4 h-4" />
          Performance
        </h2>

        <div className="flex items-start justify-between gap-4 rounded-xl border border-slate-200 px-4 py-3">
          <div className="pr-2">
            <label className="block text-sm font-medium text-slate-700">
              Parallel AI Analysis
            </label>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              Analyze multiple papers simultaneously using your existing worker pool.
              Recommended for paid Gemini API keys with higher rate limits. Free-tier keys
              use conservative defaults and may still hit model-specific request or token limits
              with this enabled.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setParallelAnalysis((value) => !value)}
            className={`relative inline-flex h-6 w-11 flex-shrink-0 rounded-full transition-colors ${
              parallelAnalysis ? 'bg-brand-600' : 'bg-slate-300'
            }`}
            aria-pressed={parallelAnalysis}
            aria-label="Toggle parallel AI analysis"
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform ${
                parallelAnalysis ? 'translate-x-5' : 'translate-x-0.5'
              } mt-0.5`}
            />
          </button>
        </div>
      </div>

      {/* About */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
          <Info className="w-4 h-4" />
          About
        </h2>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-600">Version</span>
            <span className="text-sm font-medium text-slate-900 font-mono">v{version}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-600">License</span>
            <span className="text-sm font-medium text-slate-900">MIT</span>
          </div>
          <div className="border-t border-slate-100 pt-3 flex flex-col gap-2">
            <button
              onClick={() =>
                window.api.shell.openExternal(
                  'https://github.com/michaluppal/Researchshop-Disease2Gene'
                )
              }
              className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              GitHub Repository
            </button>
            <button
              onClick={() =>
                window.api.shell.openExternal(
                  'https://github.com/michaluppal/Researchshop-Disease2Gene/issues'
                )
              }
              className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Report an Issue
            </button>
          </div>
        </div>
      </div>

      {/* Save */}
      <button
        onClick={save}
        disabled={saving || !isDirty}
        className="relative inline-flex items-center gap-2 px-6 py-2.5 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {saving ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : saved ? (
          <Check className="w-4 h-4" />
        ) : null}
        {saved ? 'Saved' : 'Save Settings'}
        {isDirty && !saving && !saved && (
          <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-amber-400 rounded-full border-2 border-white" />
        )}
      </button>
    </div>
  )
}
