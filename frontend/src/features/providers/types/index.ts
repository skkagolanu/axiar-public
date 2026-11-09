export interface ServiceResult {
  id: string;
  name: string;
  service_type: string;
  base_price_cents: number;
  duration_minutes: number;
}

export interface ProviderSearchResult {
  id: string;
  business_name: string;
  description: string | null;
  average_rating: number;
  total_reviews: number;
  service_radius_km: number;
  distance_km: number | null;
  services: ServiceResult[];
}

export interface ReviewResult {
  id: string;
  rating: number;
  comment: string | null;
  created_at: string;
}
