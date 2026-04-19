import { Component, ErrorInfo, ReactNode } from 'react'
import { AlertTriangle, RotateCcw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
  errorInfo: ErrorInfo | null
}

/**
 * Catches render/lifecycle errors anywhere in the tree and shows a recovery UI
 * instead of leaving the app stuck on a blank/partial page. In dev this is
 * especially important because HMR can apply partial updates that break a
 * component's tree — without a boundary, the whole app sits frozen.
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { error, errorInfo: null }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary] caught:', error, errorInfo)
    this.setState({ error, errorInfo })
  }

  reload = () => {
    window.location.reload()
  }

  clear = () => {
    this.setState({ error: null, errorInfo: null })
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 p-8">
          <div className="max-w-lg w-full bg-white rounded-xl shadow-sm border border-red-200 p-6 space-y-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-6 h-6 text-red-500" />
              <h2 className="text-lg font-semibold text-slate-900">Something crashed</h2>
            </div>
            <p className="text-sm text-slate-600">
              The app hit an unexpected error while rendering. Your data is safe — this only
              affects the current view. Try reloading the window.
            </p>
            <pre className="text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg p-3 overflow-auto max-h-48">
              {this.state.error.message}
              {this.state.errorInfo?.componentStack && (
                <>{'\n\n'}{this.state.errorInfo.componentStack}</>
              )}
            </pre>
            <div className="flex items-center gap-2">
              <button
                onClick={this.reload}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
                Reload window
              </button>
              <button
                onClick={this.clear}
                className="px-4 py-2 text-sm font-medium text-slate-600 rounded-lg border border-slate-300 hover:bg-slate-50 transition-colors"
              >
                Dismiss & retry
              </button>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
