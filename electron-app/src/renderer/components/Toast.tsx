import { useUIStore } from '../stores/uiStore';
import type { Toast as ToastType } from '../types';

const typeStyles: Record<ToastType['type'], string> = {
  success: 'border-l-[var(--color-success)] text-[var(--color-success)]',
  error: 'border-l-[var(--color-error)] text-[var(--color-error)]',
  warning: 'border-l-[var(--color-warning)] text-[var(--color-warning)]',
  info: 'border-l-[var(--color-primary-light)] text-[var(--color-primary-light)]',
};

const icons: Record<ToastType['type'], string> = {
  success: 'M5 13l4 4L19 7',
  error: 'M6 18L18 6M6 6l12 12',
  warning: 'M12 9v4m0 4h.01',
  info: 'M13 16h-1v-4h-1m1-4h.01',
};

function ToastItem({ toast }: { toast: ToastType }) {
  const removeToast = useUIStore((s) => s.removeToast);

  return (
    <div
      className={`
        flex items-start gap-3 bg-[var(--color-bg-card)] border border-[var(--color-border-subtle)]
        border-l-4 ${typeStyles[toast.type]} rounded-xl px-4 py-3 shadow-lg
        animate-[slideIn_0.2s_ease-out]
      `}
    >
      <svg className="h-5 w-5 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d={icons[toast.type]} />
      </svg>
      <p className="text-sm text-[var(--color-text-primary)] flex-1">{toast.message}</p>
      <button
        onClick={() => removeToast(toast.id)}
        className="text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] shrink-0 cursor-pointer"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

export function ToastContainer() {
  const toasts = useUIStore((s) => s.toasts);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 w-96">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}
