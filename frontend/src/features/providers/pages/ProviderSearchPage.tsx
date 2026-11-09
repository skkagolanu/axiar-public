import { useState } from 'react';
import api from '@/lib/axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useNavigate } from 'react-router-dom';
import type { ProviderSearchResult } from '../types';

export default function ProviderSearchPage() {
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [serviceType, setServiceType] = useState('');
  const [results, setResults] = useState<ProviderSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleSearch = async () => {
    if (!lat || !lng) {
      setError('Latitude and longitude are required');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = { lat, lng };
      if (serviceType) params.service_type = serviceType;
      const res = await api.get<ProviderSearchResult[]>('/api/v1/providers/search', { params });
      setResults(res.data);
    } catch {
      setError('Search failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-heading font-bold text-white">Find Providers</h1>

      <div className="flex flex-wrap gap-3 items-end">
        <div className="space-y-1">
          <label className="text-sm text-slate-400">Latitude</label>
          <Input
            className="w-36 bg-slate-800 text-white border-slate-700"
            placeholder="51.5074"
            value={lat}
            onChange={(e) => setLat(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm text-slate-400">Longitude</label>
          <Input
            className="w-36 bg-slate-800 text-white border-slate-700"
            placeholder="-0.1278"
            value={lng}
            onChange={(e) => setLng(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm text-slate-400">Service type (optional)</label>
          <Input
            className="w-44 bg-slate-800 text-white border-slate-700"
            placeholder="Plumbing"
            value={serviceType}
            onChange={(e) => setServiceType(e.target.value)}
          />
        </div>
        <Button
          className="bg-gradient-to-r from-violet-600 to-indigo-600 text-white"
          onClick={handleSearch}
          disabled={loading}
        >
          {loading ? 'Searching…' : 'Search'}
        </Button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {results.length === 0 && !loading && !error && (
        <p className="text-slate-500 text-sm">Enter coordinates above to find nearby providers.</p>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {results.map((p) => (
          <div
            key={p.id}
            className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-2 cursor-pointer hover:border-violet-500 transition-colors"
            onClick={() => navigate(`/dashboard/providers/${p.id}`)}
          >
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-semibold text-white leading-tight">{p.business_name}</h3>
              <span className="text-xs text-slate-400 whitespace-nowrap">
                {p.distance_km != null ? `${p.distance_km} km` : ''}
              </span>
            </div>
            {p.description && <p className="text-slate-400 text-sm line-clamp-2">{p.description}</p>}
            <div className="flex items-center gap-3 text-sm">
              <span className="text-yellow-400">★ {p.average_rating.toFixed(1)}</span>
              <span className="text-slate-500">({p.total_reviews} reviews)</span>
            </div>
            <div className="flex flex-wrap gap-1 mt-1">
              {p.services.slice(0, 3).map((s) => (
                <span key={s.id} className="text-xs bg-slate-700 text-slate-300 rounded px-2 py-0.5">
                  {s.name}
                </span>
              ))}
              {p.services.length > 3 && (
                <span className="text-xs text-slate-500">+{p.services.length - 3} more</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
