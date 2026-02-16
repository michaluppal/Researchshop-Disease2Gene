import { useUIStore } from './stores/uiStore';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Sidebar } from './components/Sidebar';
import { ToastContainer } from './components/Toast';
import { PipelineView } from './views/PipelineView';
import { ResultsView } from './views/ResultsView';
import { SettingsView } from './views/SettingsView';

function ViewRouter() {
  const activeView = useUIStore((s) => s.activeView);

  switch (activeView) {
    case 'pipeline':
      return <PipelineView />;
    case 'results':
      return <ResultsView />;
    case 'settings':
      return <SettingsView />;
  }
}

export function App() {
  return (
    <ErrorBoundary>
      <div className="flex h-full bg-[var(--color-bg-deepest)]">
        <Sidebar />
        <main className="flex-1 min-w-0 overflow-hidden">
          <ViewRouter />
        </main>
      </div>
      <ToastContainer />
    </ErrorBoundary>
  );
}
