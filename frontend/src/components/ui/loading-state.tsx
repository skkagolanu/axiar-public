import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useRequestActivity } from '@/lib/requestActivity';

interface LoadingStateProps {
  label?: string;
  className?: string;
}

export function LoadingState({
  label = 'Loading your workspace…',
  className,
}: LoadingStateProps) {
  return (
    <div
      className={cn('flex min-h-48 items-center justify-center p-8', className)}
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="relative flex h-11 w-11 items-center justify-center rounded-full bg-violet-100 text-violet-600">
          <div className="absolute inset-0 animate-ping rounded-full bg-violet-200 opacity-50" />
          <LoaderCircle className="relative h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
        <p className="text-sm font-medium text-slate-600">{label}</p>
      </div>
    </div>
  );
}

export function RequestActivityIndicator() {
  const active = useRequestActivity();

  return active ? <ActiveRequestIndicator /> : null;
}

function ActiveRequestIndicator() {
  const [visible, setVisible] = useState(false);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const showTimer = window.setTimeout(() => setVisible(true), 180);
    const slowTimer = window.setTimeout(() => setSlow(true), 2500);

    return () => {
      window.clearTimeout(showTimer);
      window.clearTimeout(slowTimer);
    };
  }, []);

  if (!visible) return null;

  return (
    <>
      <div
        className="fixed inset-x-0 top-0 z-[100] h-1 overflow-hidden bg-violet-100"
        role="progressbar"
        aria-label="Loading"
      >
        <div className="axiar-progress h-full w-1/3 rounded-full bg-gradient-to-r from-violet-600 to-indigo-500" />
      </div>
      <div
        className="fixed left-1/2 top-4 z-[100] -translate-x-1/2 rounded-full border border-violet-200 bg-white/95 px-3 py-2 text-xs font-medium text-slate-700 shadow-lg backdrop-blur"
        role="status"
        aria-live="polite"
      >
        <span className="flex items-center gap-2 whitespace-nowrap">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin text-violet-600" aria-hidden="true" />
          {slow ? 'The live demo is waking up — nearly there…' : 'Loading…'}
        </span>
      </div>
    </>
  );
}
