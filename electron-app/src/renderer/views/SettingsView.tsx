import { useEffect, useState } from 'react';
import { useSettingsStore } from '../stores/settingsStore';
import { Card } from '../components/Card';
import { Input } from '../components/Input';
import { Button } from '../components/Button';
import { PROVIDER_LABELS, type Provider } from '../types';

const PROVIDERS = Object.keys(PROVIDER_LABELS) as Provider[];

export function SettingsView() {
  const {
    apiKeys,
    entrezEmail,
    outputDir,
    maxWorkers,
    timeout,
    appVersion,
    loadSettings,
    saveApiKey,
    deleteApiKey,
    updateSetting,
    saveAllSettings,
  } = useSettingsStore();

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">
        Settings
      </h1>

      {/* API Keys */}
      <Card title="API Keys" subtitle="Configure credentials for AI providers">
        <div className="space-y-4">
          {PROVIDERS.map((provider) => (
            <ApiKeyCard
              key={provider}
              provider={provider}
              label={PROVIDER_LABELS[provider]}
              info={apiKeys[provider]}
              onSave={(key) => saveApiKey(provider, key)}
              onDelete={() => deleteApiKey(provider)}
            />
          ))}
        </div>
      </Card>

      {/* General Settings */}
      <Card title="General Settings">
        <div className="space-y-4">
          <Input
            label="Entrez Email"
            placeholder="your@email.com (required for NCBI API)"
            value={entrezEmail}
            onChange={(e) => updateSetting('entrezEmail', e.target.value)}
          />
          <Input
            label="Output Directory"
            placeholder="/path/to/output"
            value={outputDir}
            onChange={(e) => updateSetting('outputDir', e.target.value)}
          />
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Max Workers"
              type="number"
              min={1}
              max={10}
              value={maxWorkers}
              onChange={(e) => updateSetting('maxWorkers', Number(e.target.value))}
            />
            <Input
              label="Timeout (seconds)"
              type="number"
              min={30}
              max={600}
              value={timeout}
              onChange={(e) => updateSetting('timeout', Number(e.target.value))}
            />
          </div>
          <div className="pt-2">
            <Button onClick={saveAllSettings}>Save Settings</Button>
          </div>
        </div>
      </Card>

      {/* About */}
      <Card title="About">
        <div className="space-y-2 text-sm text-[var(--color-text-secondary)]">
          <p>
            <span className="text-[var(--color-text-muted)]">Version:</span>{' '}
            {appVersion || '1.0.0'}
          </p>
          <p>
            <span className="text-[var(--color-text-muted)]">Platform:</span>{' '}
            {window.electronAPI?.getPlatform?.() ?? 'unknown'}
          </p>
          <p className="text-[var(--color-text-muted)] pt-2">
            AI-powered gene-disease association extraction from biomedical literature.
          </p>
        </div>
      </Card>
    </div>
  );
}

function ApiKeyCard({
  provider,
  label,
  info,
  onSave,
  onDelete,
}: {
  provider: string;
  label: string;
  info: { configured: boolean; maskedKey: string } | undefined;
  onSave: (key: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [keyValue, setKeyValue] = useState('');
  const [showKey, setShowKey] = useState(false);
  const configured = info?.configured ?? false;

  function handleSave() {
    if (keyValue.trim()) {
      onSave(keyValue.trim());
      setKeyValue('');
      setEditing(false);
    }
  }

  return (
    <div className="flex items-center justify-between p-4 rounded-xl bg-[var(--color-bg-surface)] border border-[var(--color-border-subtle)]">
      <div className="flex items-center gap-3 min-w-0">
        <div
          className={`h-2.5 w-2.5 rounded-full shrink-0 ${
            configured ? 'bg-[var(--color-success)]' : 'bg-[var(--color-text-muted)]'
          }`}
        />
        <div className="min-w-0">
          <p className="text-sm font-medium text-[var(--color-text-primary)]">{label}</p>
          {configured && !editing && (
            <p className="text-xs text-[var(--color-text-muted)] font-mono truncate">
              {showKey ? info?.maskedKey : '••••••••'}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {editing ? (
          <>
            <input
              type="password"
              placeholder="Enter API key"
              value={keyValue}
              onChange={(e) => setKeyValue(e.target.value)}
              className="rounded-lg bg-[var(--color-bg-card)] border border-[var(--color-border-subtle)] text-[var(--color-text-primary)] px-3 py-1.5 text-sm w-56 focus:outline-none focus:border-[var(--color-primary)]"
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            />
            <Button size="sm" onClick={handleSave}>
              Save
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditing(false);
                setKeyValue('');
              }}
            >
              Cancel
            </Button>
          </>
        ) : (
          <>
            {configured && (
              <>
                <button
                  onClick={() => setShowKey(!showKey)}
                  className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] cursor-pointer"
                >
                  {showKey ? 'Hide' : 'Show'}
                </button>
                <Button size="sm" variant="danger" onClick={onDelete}>
                  Delete
                </Button>
              </>
            )}
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setEditing(true)}
            >
              {configured ? 'Update' : 'Configure'}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
