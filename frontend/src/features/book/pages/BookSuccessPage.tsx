import { CheckCircle, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export default function BookSuccessPage() {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-600 text-white">
          <CheckCircle className="h-9 w-9" />
        </div>
        <h1 className="font-heading text-2xl font-bold text-slate-900">Booking received!</h1>
        <p className="mt-2 text-slate-500">
          We've sent a confirmation link to your email. Click it to view or manage your booking.
        </p>
        <div className="mt-6 flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
          <Mail className="h-4 w-4 text-violet-600" />
          Check your inbox — the link expires in 24 hours.
        </div>
        <Button asChild variant="outline" className="mt-6">
          <Link to="/login">Sign in to your account</Link>
        </Button>
      </div>
    </div>
  );
}
