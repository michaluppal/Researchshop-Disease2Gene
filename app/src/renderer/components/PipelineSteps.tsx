import { Search, Filter, Cpu, BarChart3, Check, Loader2 } from 'lucide-react'

interface Step {
  id: string
  label: string
  description: string
  activeDescription: string
  icon: React.ElementType
  stages: string[]
}

const STEPS: Step[] = [
  {
    id: 'search',
    label: 'Search',
    description: 'Finding papers',
    activeDescription: 'Querying PubMed and fetching paper content',
    icon: Search,
    stages: [
      'Searching PubMed',
      'Fetching paper details',
      'Fetching full text',
      'Processing fetched content',
      'Running PubTator',
      'Fetching citation',
      'Starting',
      'Initializing',
    ],
  },
  {
    id: 'screen',
    label: 'Screen',
    description: 'Filtering papers',
    activeDescription: 'Scoring papers for gene relevance',
    icon: Filter,
    stages: ['Screening abstracts', 'Selecting top papers'],
  },
  {
    id: 'extract',
    label: 'Extract',
    description: 'AI analysis',
    activeDescription: 'Running Gemini AI analysis on each paper',
    icon: Cpu,
    stages: ['Analyzing papers with AI', 'Enriching gene'],
  },
  {
    id: 'synthesize',
    label: 'Synthesize',
    description: 'Building results',
    activeDescription: 'Validating genes and building final CSV',
    icon: BarChart3,
    stages: ['Finalizing results', 'Completed'],
  },
]

function getStepStatus(
  step: Step,
  currentStage: string,
  isRunning: boolean
): 'pending' | 'active' | 'done' {
  const currentStepIndex = STEPS.findIndex((s) =>
    s.stages.some((stage) => currentStage.toLowerCase().includes(stage.toLowerCase()))
  )
  const stepIndex = STEPS.indexOf(step)

  if (!isRunning && currentStage === 'Completed') return 'done'
  if (currentStepIndex < 0) return stepIndex === 0 && isRunning ? 'active' : 'pending'
  if (stepIndex < currentStepIndex) return 'done'
  if (stepIndex === currentStepIndex) return 'active'
  return 'pending'
}

interface PipelineStepsProps {
  stage: string
  percent: number
  isRunning: boolean
}

export default function PipelineSteps({ stage, percent, isRunning }: PipelineStepsProps) {
  return (
    <div className="space-y-0">
      {STEPS.map((step, i) => {
        const status = getStepStatus(step, stage, isRunning)
        const Icon = step.icon
        return (
          <div key={step.id} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <div
                className={`w-9 h-9 rounded-full flex items-center justify-center transition-colors ${
                  status === 'done'
                    ? 'bg-emerald-100 text-emerald-600'
                    : status === 'active'
                      ? 'bg-brand-100 text-brand-600 ring-2 ring-brand-200 animate-pulse'
                      : 'bg-slate-100 text-slate-400'
                }`}
              >
                {status === 'done' ? (
                  <Check className="w-4 h-4" />
                ) : status === 'active' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Icon className="w-4 h-4" />
                )}
              </div>
              {i < STEPS.length - 1 && (
                <div
                  className={`w-0.5 h-6 my-1 transition-colors ${
                    status === 'done' ? 'bg-emerald-200' : 'bg-slate-200'
                  }`}
                />
              )}
            </div>
            <div className="pt-1">
              <p
                className={`text-sm font-medium leading-tight ${
                  status === 'active'
                    ? 'text-brand-700'
                    : status === 'done'
                      ? 'text-emerald-700'
                      : 'text-slate-400'
                }`}
              >
                {step.label}
              </p>
              <p className={`text-xs mt-0.5 ${
                status === 'active'
                  ? 'text-brand-500'
                  : status === 'done'
                    ? 'text-emerald-500'
                    : 'text-slate-400'
              }`}>
                {status === 'active' ? step.activeDescription : status === 'done' ? 'Done' : step.description}
              </p>
              {status === 'active' && (
                <div className="mt-2 w-full">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-brand-500 rounded-full transition-all duration-500"
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-brand-500 tabular-nums flex-shrink-0">
                      {Math.round(percent)}%
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
