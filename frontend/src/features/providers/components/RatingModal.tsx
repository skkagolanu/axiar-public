import { useState } from 'react';
import api from '@/lib/axios';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

interface RatingModalProps {
  bookingId: string;
  providerId: string;
  onDone: () => void;
}

export function RatingModal({ bookingId, providerId, onDone }: RatingModalProps) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (rating === 0) {
      setError('Please select a rating');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.post('/api/v1/reviews', {
        booking_id: bookingId,
        provider_id: providerId,
        rating,
        comment: comment.trim() || null,
      });
      onDone();
    } catch {
      setError('Failed to submit rating. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open onOpenChange={() => onDone()}>
      <DialogContent className="bg-slate-900 border-slate-700 text-white max-w-sm">
        <DialogHeader>
          <DialogTitle className="font-heading">Rate this service</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex gap-2 justify-center">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                className={`text-3xl transition-transform hover:scale-110 ${n <= rating ? 'text-yellow-400' : 'text-slate-600'}`}
                onClick={() => setRating(n)}
              >
                ★
              </button>
            ))}
          </div>
          <textarea
            className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-sm text-white placeholder-slate-500 resize-none"
            rows={3}
            placeholder="Optional comment…"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <div className="flex gap-2">
            <Button variant="outline" className="flex-1 border-slate-700 text-slate-300" onClick={onDone}>
              Skip
            </Button>
            <Button
              className="flex-1 bg-gradient-to-r from-violet-600 to-indigo-600 text-white"
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? 'Submitting…' : 'Submit'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
