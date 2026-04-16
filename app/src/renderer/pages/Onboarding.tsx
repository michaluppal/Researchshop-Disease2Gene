import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Key,
  Mail,
  Loader2,
  Check,
  AlertCircle,
  Shield,
  Rocket,
} from 'lucide-react'

const STEPS = [
  { label: 'Disclaimer', icon: Shield },
  { label: 'Welcome', icon: Rocket },
  { label: 'API Key', icon: Key },
  { label: 'Email', icon: Mail },
] as const

export default function Onboarding() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [geminiKey, setGeminiKey] = useState('')
  const [entrezEmail, setEntrezEmail] = useState('')
  const [validating, setValidating] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)
  const [keyValid, setKeyValid] = useState(false)
  const [disclaimerAcknowledged, setDisclaimerAcknowledged] = useState(false)
  const [transitioning, setTransitioning] = useState(false)
  const [direction, setDirection] = useState<'forward' | 'back'>('forward')
  const contentRef = useRef<HTMLDivElement>(null)

  const goToStep = (target: number) => {
    setDirection(target > step ? 'forward' : 'back')
    setTransitioning(true)
  }

  useEffect(() => {
    if (!transitioning) return
    const timer = setTimeout(() => {
      setStep((prev) => (direction === 'forward' ? prev + 1 : prev - 1))
      setTransitioning(false)
    }, 200)
    return () => clearTimeout(timer)
  }, [transitioning, direction])

  const validateKey = async () => {
    setValidating(true)
    setKeyError(null)
    const result = await window.api.settings.validateGeminiKey(geminiKey)
    setValidating(false)
    if (result.valid) {
      setKeyValid(true)
      setKeyError(null)
    } else {
      setKeyError(result.error || 'Invalid API key')
      setKeyValid(false)
    }
  }

  const finish = async () => {
    await window.api.settings.set('geminiApiKey', geminiKey)
    await window.api.settings.set('entrezEmail', entrezEmail)
    await window.api.settings.set('onboardingComplete', true)
    navigate('/query')
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      <div className="w-full max-w-lg px-4">
        {/* Step indicator */}
        <div className="flex items-center justify-center mb-10">
          {STEPS.map((s, i) => {
            const Icon = s.icon
            const isCompleted = i < step
            const isCurrent = i === step
            return (
              <div key={i} className="flex items-center">
                <div className="flex flex-col items-center">
                  <div
                    className={`w-9 h-9 rounded-full flex items-center justify-center transition-all duration-300 ${
                      isCompleted
                        ? 'bg-brand-600 text-white'
                        : isCurrent
                          ? 'bg-brand-600 text-white ring-4 ring-brand-100'
                          : 'bg-slate-200 text-slate-400'
                    }`}
                  >
                    {isCompleted ? (
                      <Check className="w-4 h-4" />
                    ) : (
                      <Icon className="w-4 h-4" />
                    )}
                  </div>
                  <span
                    className={`text-xs mt-1.5 font-medium transition-colors duration-300 ${
                      isCurrent ? 'text-brand-600' : isCompleted ? 'text-brand-500' : 'text-slate-400'
                    }`}
                  >
                    {s.label}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    className={`w-12 h-0.5 mx-1.5 -mt-5 transition-colors duration-300 ${
                      i < step ? 'bg-brand-600' : 'bg-slate-200'
                    }`}
                  />
                )}
              </div>
            )
          })}
        </div>

        {/* Content card */}
        <div
          ref={contentRef}
          className={`bg-white rounded-2xl shadow-sm border border-slate-100 p-8 transition-all duration-200 ${
            transitioning
              ? 'opacity-0 translate-x-' + (direction === 'forward' ? '4' : '-4')
              : 'opacity-100 translate-x-0'
          }`}
          style={{
            transform: transitioning
              ? `translateX(${direction === 'forward' ? '16px' : '-16px'})`
              : 'translateX(0)',
            opacity: transitioning ? 0 : 1,
            transition: 'opacity 200ms ease, transform 200ms ease',
          }}
        >
          {step === 0 && (
            <div>
              <div className="flex items-center gap-3 mb-5">
                <div className="w-11 h-11 bg-amber-100 rounded-xl flex items-center justify-center">
                  <Shield className="w-5 h-5 text-amber-600" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Research Use Only</h2>
                  <p className="text-sm text-slate-500">Please read before continuing</p>
                </div>
              </div>
              <div className="bg-amber-50 border-l-4 border-amber-400 rounded-r-lg p-4 mb-6 text-sm text-amber-900 space-y-2">
                <p>
                  ResearchShop is a <strong>research tool</strong> for literature analysis. It is{' '}
                  <strong>not validated for clinical or diagnostic use</strong>.
                </p>
                <p>
                  AI-extracted gene/variant associations must be independently verified before use in
                  publications, clinical decisions, or downstream analyses.
                </p>
                <p>
                  False associations can propagate into the scientific record. Always cross-check
                  findings against HGNC, ClinVar, and primary literature.
                </p>
              </div>
              <label className="flex items-center gap-3 cursor-pointer mb-6 group">
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={disclaimerAcknowledged}
                  onClick={() => setDisclaimerAcknowledged(!disclaimerAcknowledged)}
                  className={`w-5 h-5 rounded flex-shrink-0 flex items-center justify-center border-2 transition-colors ${
                    disclaimerAcknowledged
                      ? 'bg-brand-600 border-brand-600'
                      : 'border-slate-300 group-hover:border-brand-400'
                  }`}
                >
                  {disclaimerAcknowledged && <Check className="w-3.5 h-3.5 text-white" />}
                </button>
                <span className="text-sm text-slate-700 select-none">
                  I understand this tool is for research use only and results require expert review
                </span>
              </label>
              <button
                onClick={() => goToStep(1)}
                disabled={!disclaimerAcknowledged}
                className="w-full inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Continue
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {step === 1 && (
            <div className="text-center">
              <div className="w-16 h-16 bg-brand-50 rounded-2xl flex items-center justify-center mx-auto mb-6 border border-brand-100">
                <Rocket className="w-8 h-8 text-brand-600" />
              </div>
              <h2 className="text-2xl font-bold text-slate-900 mb-3">Welcome to ResearchShop</h2>
              <p className="text-slate-500 mb-8 leading-relaxed">
                AI-powered biomedical research analysis running entirely on your machine. Submit
                PubMed queries and get structured gene/variant data extracted from papers.
              </p>
              <div className="flex justify-between">
                <button
                  onClick={() => goToStep(-1)}
                  className="px-4 py-2.5 text-sm font-medium rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={() => goToStep(2)}
                  className="inline-flex items-center gap-2 px-6 py-2.5 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 transition-colors"
                >
                  Get Started
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <div className="flex items-center gap-3 mb-6">
                <div className="w-11 h-11 bg-brand-50 rounded-xl flex items-center justify-center border border-brand-100">
                  <Key className="w-5 h-5 text-brand-600" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Gemini API Key</h2>
                  <p className="text-sm text-slate-500">Required for AI paper analysis</p>
                </div>
              </div>
              <input
                type="password"
                value={geminiKey}
                onChange={(e) => {
                  setGeminiKey(e.target.value)
                  setKeyValid(false)
                  setKeyError(null)
                }}
                placeholder="Enter your Gemini API key"
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 mb-2"
              />
              {keyError && (
                <p className="flex items-center gap-1 text-sm text-red-500 mb-2">
                  <AlertCircle className="w-4 h-4" />
                  {keyError}
                </p>
              )}
              {keyValid && (
                <p className="flex items-center gap-1 text-sm text-green-600 mb-2">
                  <Check className="w-4 h-4" />
                  API key is valid
                </p>
              )}
              <button
                onClick={validateKey}
                disabled={!geminiKey || validating}
                className="w-full mb-4 px-4 py-2 text-sm font-medium rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-40 transition-colors"
              >
                {validating ? (
                  <Loader2 className="w-4 h-4 animate-spin mx-auto" />
                ) : (
                  'Validate Key'
                )}
              </button>
              <p className="text-xs text-slate-400 mb-6">
                Get a free API key at{' '}
                <button
                  onClick={() =>
                    window.api.shell.openExternal('https://aistudio.google.com/app/apikey')
                  }
                  className="text-brand-600 hover:underline"
                >
                  aistudio.google.com
                </button>
              </p>
              <div className="flex justify-between">
                <button
                  onClick={() => goToStep(-1)}
                  className="px-4 py-2.5 text-sm font-medium rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={() => goToStep(3)}
                  disabled={!keyValid}
                  className="inline-flex items-center gap-2 px-6 py-2.5 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div>
              <div className="flex items-center gap-3 mb-6">
                <div className="w-11 h-11 bg-brand-50 rounded-xl flex items-center justify-center border border-brand-100">
                  <Mail className="w-5 h-5 text-brand-600" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-900">NCBI / Entrez Email</h2>
                  <p className="text-sm text-slate-500">Required by NCBI for PubMed API access</p>
                </div>
              </div>
              <input
                type="email"
                value={entrezEmail}
                onChange={(e) => setEntrezEmail(e.target.value)}
                placeholder="your@email.com"
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 mb-2"
              />
              <p className="text-xs text-slate-400 mb-6">
                NCBI requires an email for API usage identification. This is never shared.
              </p>
              <div className="flex justify-between">
                <button
                  onClick={() => goToStep(-1)}
                  className="px-4 py-2.5 text-sm font-medium rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={finish}
                  disabled={!entrezEmail}
                  className="inline-flex items-center gap-2 px-6 py-2.5 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Complete Setup
                  <Check className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
