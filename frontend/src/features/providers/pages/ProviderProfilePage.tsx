import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '@/lib/axios';
import type { ProviderSearchResult, ReviewResult } from '../types';
import { LoadingState } from '@/components/ui/loading-state';

export default function ProviderProfilePage() {
  const { providerId } = useParams<{ providerId: string }>();
  const [provider, setProvider] = useState<ProviderSearchResult | null>(null);
  const [reviews, setReviews] = useState<ReviewResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!providerId) return;
    let cancelled = false;
    Promise.all([
      api.get<ProviderSearchResult>(`/api/v1/providers/${providerId}`),
      api.get<ReviewResult[]>(`/api/v1/reviews?provider_id=${providerId}`).catch(() => ({ data: [] as ReviewResult[] })),
    ])
      .then(([provRes, revRes]) => {
        if (!cancelled) {
          setProvider(provRes.data);
          setReviews(revRes.data);
        }
      })
      .catch(() => { if (!cancelled) setError('Could not load provider profile.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [providerId]);

  if (loading) return <LoadingState label="Loading provider profile…" />;
  if (error || !provider) return <div className="p-6 text-red-400">{error ?? 'Provider not found'}</div>;

  return (
    <div className="p-6 space-y-8 max-w-3xl">
      <div className="space-y-2">
        <h1 className="text-2xl font-heading font-bold text-white">{provider.business_name}</h1>
        {provider.description && <p className="text-slate-400">{provider.description}</p>}
        <div className="flex items-center gap-4 text-sm">
          <span className="text-yellow-400">★ {provider.average_rating.toFixed(1)}</span>
          <span className="text-slate-500">{provider.total_reviews} reviews</span>
          <span className="text-slate-500">Radius: {provider.service_radius_km} km</span>
        </div>
      </div>

      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-white">Services</h2>
        {provider.services.length === 0 ? (
          <p className="text-slate-500 text-sm">No services listed.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {provider.services.map((s) => (
              <div key={s.id} className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-1">
                <div className="flex justify-between items-start">
                  <span className="font-medium text-white">{s.name}</span>
                  <span className="text-violet-400 text-sm font-semibold">
                    £{(s.base_price_cents / 100).toFixed(2)}
                  </span>
                </div>
                <p className="text-xs text-slate-400">{s.service_type} · {s.duration_minutes} min</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-white">Reviews</h2>
        {reviews.length === 0 ? (
          <p className="text-slate-500 text-sm">No reviews yet.</p>
        ) : (
          <div className="space-y-3">
            {reviews.map((r) => (
              <div key={r.id} className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-yellow-400">{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</span>
                  <span className="text-xs text-slate-500">{new Date(r.created_at).toLocaleDateString('en-GB')}</span>
                </div>
                {r.comment && <p className="text-slate-300 text-sm">{r.comment}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
