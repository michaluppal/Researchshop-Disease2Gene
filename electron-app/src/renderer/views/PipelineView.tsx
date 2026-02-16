import { useCallback, useEffect, useRef, useState } from 'react';
import { usePipelineStore } from '../stores/pipelineStore';
import { useResultsStore } from '../stores/resultsStore';
import { useUIStore } from '../stores/uiStore';
import { Button } from '../components/Button';
import { Input, Textarea } from '../components/Input';
import { Card } from '../components/Card';
import { LoadingSpinner } from '../components/LoadingSpinner';
import {
  PROVIDER_LABELS,
  PROVIDER_MODELS,
  type Provider,
  type CustomColumn,
} from '../types';

export function PipelineView() {
  const config = usePipelineStore((s) => s.config);
  const setConfig = usePipelineStore((s) => s.setConfig);
  const isRunning = usePipelineStore((s) => s.isRunning);
  const stage = usePipelineStore((s) => s.stage);
  const progress = usePipelineStore((s) => s.progress);
  const logs = usePipelineStore((s) => s.logs);
  const startPipeline = usePipelineStore((s) => s.startPipeline);
  const stopPipeline = usePipelineStore((s) => s.stopPipeline);
  const addLog = usePipelineStore((s) => s.addLog);
  const setProgress = usePipelineStore((s) => s.setProgress);
  const setResults = useResultsStore((s) => s.setResults);
  const setActiveView = useUIStore((s) => s.setActiveView);
  const addToast = useUIStore((s) => s.addToast);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  // IPC listeners
  useEffect(() => {
    const unsubProgress = window.electronAPI.onPipelineProgress((data) => {
      setProgress(data.stage, data.progress);
      if (data.message) addLog(data.message);
    });
    const unsubResult = window.electronAPI.onPipelineResult((data) => {
      setResults(data.results);
      usePipelineStore.setState({ isRunning: false, stage: 'Complete', progress: 100 });
      addToast({ type: 'success', message: `Pipeline complete: ${data.results.length} results found` });
      setActiveView('results');
    });
    const unsubError = window.electronAPI.onPipelineError((data) => {
      usePipelineStore.setState({ isRunning: false });
      addToast({ type: 'error', message: data.message });
      addLog(`ERROR: ${data.message}`);
    });
    return () => {
      unsubProgress();
      unsubResult();
      unsubError();
    };
  }, [addLog, addToast, setActiveView, setProgress, setResults]);

  const handleProviderChange = useCallback(
    (provider: Provider) => {
      const models = PROVIDER_MODELS[provider];
      setConfig({ provider, model: models[0] ?? '' });
    },
    [setConfig],
  );

  // Custom columns
  const addColumn = useCallback(() => {
    const col: CustomColumn = { id: crypto.randomUUID(), name: '', description: '' };
    setConfig({ customColumns: [...config.customColumns, col] });
  }, [config.customColumns, setConfig]);

  const updateColumn = useCallback(
    (id: string, field: 'name' | 'description', value: string) => {
      setConfig({
        customColumns: config.customColumns.map((c) =>
          c.id === id ? { ...c, [field]: value } : c,
        ),
      });
    },
    [config.customColumns, setConfig],
  );

  const removeColumn = useCallback(
    (id: string) => {
      setConfig({ customColumns: config.customColumns.filter((c) => c.id !== id) });
    },
    [config.customColumns, setConfig],
  );

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">
        Pipeline Configuration
      </h1>

      {/* Search inputs */}
      <Card title="Search Parameters" subtitle="Define what to search in PubMed">
        <div className="space-y-4">
          <Textarea
            label="PubMed Query"
            placeholder='e.g. "multisystem inflammatory syndrome" AND "children" AND "gene"'
            rows={3}
            value={config.query}
            onChange={(e) => setConfig({ query: e.target.value })}
          />
          <Input
            label="Specific PMIDs"
            placeholder="Comma-separated: 12345678, 23456789"
            value={config.pmids}
            onChange={(e) => setConfig({ pmids: e.target.value })}
          />
          <Input
            label="Author Search"
            placeholder="e.g. Smith J"
            value={config.authorSearch}
            onChange={(e) => setConfig({ authorSearch: e.target.value })}
          />
        </div>
      </Card>

      {/* AI Configuration */}
      <Card title="AI Configuration" subtitle="Select the AI provider and model">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
              Provider
            </label>
            <select
              value={config.provider}
              onChange={(e) => handleProviderChange(e.target.value as Provider)}
              className="w-full rounded-xl bg-[var(--color-bg-surface)] border border-[var(--color-border-subtle)] text-[var(--color-text-primary)] px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--color-primary)] focus:ring-1 focus:ring-[var(--color-primary)]"
            >
              {(Object.entries(PROVIDER_LABELS) as [Provider, string][]).map(
                ([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ),
              )}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
              Model
            </label>
            <select
              value={config.model}
              onChange={(e) => setConfig({ model: e.target.value })}
              className="w-full rounded-xl bg-[var(--color-bg-surface)] border border-[var(--color-border-subtle)] text-[var(--color-text-primary)] px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--color-primary)] focus:ring-1 focus:ring-[var(--color-primary)]"
            >
              {PROVIDER_MODELS[config.provider]?.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Parameters */}
      <Card title="Parameters">
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
              Max Results: {config.maxResults}
            </label>
            <input
              type="range"
              min={10}
              max={500}
              step={10}
              value={config.maxResults}
              onChange={(e) => setConfig({ maxResults: Number(e.target.value) })}
              className="w-full accent-[var(--color-primary)]"
            />
            <div className="flex justify-between text-xs text-[var(--color-text-muted)]">
              <span>10</span>
              <span>500</span>
            </div>
          </div>
          <div className="space-y-2">
            <label className="block text-sm font-medium text-[var(--color-text-secondary)]">
              Top N Cited: {config.topNCited}
            </label>
            <input
              type="range"
              min={5}
              max={100}
              step={5}
              value={config.topNCited}
              onChange={(e) => setConfig({ topNCited: Number(e.target.value) })}
              className="w-full accent-[var(--color-primary)]"
            />
            <div className="flex justify-between text-xs text-[var(--color-text-muted)]">
              <span>5</span>
              <span>100</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Custom Columns */}
      <Card
        title="Custom Columns"
        subtitle="Define additional data columns to extract"
      >
        <div className="space-y-3">
          {config.customColumns.map((col) => (
            <div key={col.id} className="flex items-start gap-3">
              <Input
                placeholder="Column name"
                value={col.name}
                onChange={(e) => updateColumn(col.id, 'name', e.target.value)}
                className="flex-1"
              />
              <Input
                placeholder="Description for AI"
                value={col.description}
                onChange={(e) => updateColumn(col.id, 'description', e.target.value)}
                className="flex-[2]"
              />
              <button
                onClick={() => removeColumn(col.id)}
                className="mt-1 p-2 text-[var(--color-text-muted)] hover:text-[var(--color-error)] transition-colors cursor-pointer"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
          <Button variant="ghost" size="sm" onClick={addColumn}>
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            Add Column
          </Button>
        </div>
      </Card>

      {/* Run Controls */}
      <div className="flex items-center gap-4">
        {!isRunning ? (
          <Button
            variant="primary"
            size="lg"
            onClick={startPipeline}
            disabled={!config.query && !config.pmids && !config.authorSearch}
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 3l14 9-14 9V3z" />
            </svg>
            Run Pipeline
          </Button>
        ) : (
          <Button variant="danger" size="lg" onClick={stopPipeline}>
            <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="1" />
            </svg>
            Stop
          </Button>
        )}
      </div>

      {/* Progress */}
      {(isRunning || stage) && (
        <Card>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              {isRunning && <LoadingSpinner size="sm" />}
              <span className="text-sm font-medium text-[var(--color-text-primary)]">
                {stage}
              </span>
              <span className="text-sm text-[var(--color-text-muted)] ml-auto">
                {progress}%
              </span>
            </div>
            <div className="w-full h-2 bg-[var(--color-bg-surface)] rounded-full overflow-hidden">
              <div
                className="h-full bg-[var(--color-primary)] rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </Card>
      )}

      {/* Logs */}
      {logs.length > 0 && (
        <Card title="Logs">
          <div
            ref={logContainerRef}
            className="h-64 overflow-y-auto rounded-xl bg-[var(--color-bg-deepest)] p-4 font-mono text-xs leading-relaxed text-[var(--color-text-secondary)]"
          >
            {logs.map((log, i) => (
              <div key={i} className="whitespace-pre-wrap">
                <span className="text-[var(--color-text-muted)] select-none mr-3">
                  {String(i + 1).padStart(3, ' ')}
                </span>
                {log}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
