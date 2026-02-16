import { type ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
}

export function Card({ children, className = '', title, subtitle }: CardProps) {
  return (
    <div
      className={`
        bg-[var(--color-bg-card)] border border-[var(--color-border-subtle)]
        rounded-2xl p-6 ${className}
      `}
    >
      {title && (
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
            {title}
          </h3>
          {subtitle && (
            <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
              {subtitle}
            </p>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
