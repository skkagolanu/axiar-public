import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { CheckCircle, XCircle, Loader2 } from 'lucide-react';
import api from '@/lib/axios';
import { Button } from '@/components/ui/button';

export default function BookConfirmPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>(token ? 'loading' : 'error');

  useEffect(() => {
    if (!token) return;
    // Verify the magic link token — this logs the guest in and proves booking ownership
    api.post('/api/v1/auth/verify-magic-link', null, { params: { token } })
      .then(() => setStatus('ok'))
      .catch(() => setStatus('error'));
  }, [token]);

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-violet-600" />
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
        <div className="max-w-md w-full text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-100 text-red-600">
            <XCircle className="h-9 w-9" />
          </div>
          <h1 className="font-heading text-2xl font-bold text-slate-900">Link expired</h1>
          <p className="mt-2 text-slate-500">This confirmation link is invalid or has expired. Book again to get a new one.</p>
          <Button asChild className="mt-6 bg-gradient-to-r from-violet-600 to-indigo-600 text-white">
            <Link to="/book">Book again</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-600 text-white">
          <CheckCircle className="h-9 w-9" />
        </div>
        <h1 className="font-heading text-2xl font-bold text-slate-900">You're verified!</h1>
        <p className="mt-2 text-slate-500">Your booking is confirmed. You can now view all your bookings.</p>
        <Button asChild className="mt-6 bg-gradient-to-r from-violet-600 to-indigo-600 text-white">
          <Link to="/dashboard/jobs">View bookings</Link>
        </Button>
      </div>
    </div>
  );
}
