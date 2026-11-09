import { useEffect } from 'react';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

// Lightweight, dependency-free toast surface wired to the existing use-toast hook.
// Mounted once at the app root so any `toast(...)` call becomes visible to the user.
export function Toaster() {
  const { toasts, dismiss } = useToast();

  // Auto-dismiss each open toast after a few seconds (the hook's own remove delay is long).
  useEffect(() => {
    const timers = toasts
      .filter((t: any) => t.open)
      .map((t: any) => window.setTimeout(() => dismiss(t.id), 4000));
    return () => timers.forEach(clearTimeout);
  }, [toasts, dismiss]);

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
      {toasts
        .filter((t: any) => t.open)
        .map((t: any) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              'pointer-events-auto rounded-lg border p-4 shadow-lg transition-all',
              t.variant === 'destructive'
                ? 'border-red-500/50 bg-red-600 text-white'
                : 'border-slate-200 bg-white text-slate-900'
            )}
          >
            <div className="flex items-start gap-3">
              <div className="flex-1">
                {t.title && <div className="text-sm font-semibold">{t.title}</div>}
                {t.description && <div className="text-sm opacity-90">{t.description}</div>}
              </div>
              <button
                onClick={() => dismiss(t.id)}
                className="text-sm opacity-70 hover:opacity-100"
                aria-label="Close"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
    </div>
  );
}
