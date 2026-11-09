import axios from 'axios';
import { useAuthStore } from '@/store/useAuthStore';
import { beginRequest, endRequest } from '@/lib/requestActivity';

type TrackedRequestConfig = {
  __activityTracked?: boolean;
};

// baseURL is intentionally empty by default: pages call absolute paths
// (e.g. '/api/v1/auth/login'), and in dev MSW intercepts the short mock paths
// by suffix. Set VITE_API_URL to point the app at a real backend origin.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
});

// Attach the persisted JWT (from the zustand auth store) to every request.
api.interceptors.request.use((config) => {
  (config as TrackedRequestConfig).__activityTracked = true;
  beginRequest();
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (import.meta.env.VITE_DEMO_MODE === 'true') {
    config.headers['X-Tenant-Slug'] = 'demo';
  }
  return config;
});

api.interceptors.response.use(
  (response) => {
    if ((response.config as TrackedRequestConfig).__activityTracked) {
      endRequest();
    }
    return response;
  },
  (error) => {
    if ((error.config as TrackedRequestConfig | undefined)?.__activityTracked) {
      endRequest();
    }
    return Promise.reject(error);
  },
);

export default api;
