import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AuthLayout from '@/components/layout/AuthLayout';
import DashboardLayout from '@/components/layout/DashboardLayout';
import ProtectedRoute from '@/components/layout/ProtectedRoute';
import { WebSocketProvider } from '@/providers/WebSocketProvider';
import { Toaster } from '@/components/ui/toaster';
import { LoadingState, RequestActivityIndicator } from '@/components/ui/loading-state';
import LoginPage from '@/features/auth/pages/LoginPage';
import RegisterPage from '@/features/auth/pages/RegisterPage';
const DashboardPage = lazy(() => import('@/features/dashboard/pages/DashboardPage'));
const JobsPage = lazy(() => import('@/features/jobs/pages/JobsPage'));
const SchedulePage = lazy(() => import('@/features/schedule/pages/SchedulePage'));
const TeamPage = lazy(() => import('@/features/team/pages/TeamPage'));
const FieldLayout = lazy(() => import('@/features/mobile/layouts/FieldLayout'));
const MobileJobsPage = lazy(() => import('@/features/mobile/pages/MobileJobsPage'));
const CustomersPage = lazy(() => import('@/features/customers/pages/CustomersPage'));
const ReportsPage = lazy(() => import('@/features/reports/pages/ReportsPage'));
const AssistantPage = lazy(() => import('@/features/assistant/pages/AssistantPage'));
const ProviderSearchPage = lazy(() => import('@/features/providers/pages/ProviderSearchPage'));
const ProviderProfilePage = lazy(() => import('@/features/providers/pages/ProviderProfilePage'));
const BookPage = lazy(() => import('@/features/book/pages/BookPage'));
const BookSuccessPage = lazy(() => import('@/features/book/pages/BookSuccessPage'));
const BookConfirmPage = lazy(() => import('@/features/book/pages/BookConfirmPage'));

function App() {
  return (
    <WebSocketProvider>
      <BrowserRouter>
        <Suspense fallback={<LoadingState />}>
          <Routes>
            <Route element={<AuthLayout />}>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
            </Route>

            <Route element={<ProtectedRoute />}>
              <Route element={<DashboardLayout />}>
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/dashboard/jobs" element={<JobsPage />} />
                <Route path="/dashboard/schedule" element={<SchedulePage />} />
                <Route path="/dashboard/team" element={<TeamPage />} />
                <Route path="/dashboard/customers" element={<CustomersPage />} />
                <Route path="/dashboard/reports" element={<ReportsPage />} />
                <Route path="/dashboard/assistant" element={<AssistantPage />} />
                <Route path="/dashboard/providers" element={<ProviderSearchPage />} />
                <Route path="/dashboard/providers/:providerId" element={<ProviderProfilePage />} />
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
              </Route>
            </Route>

            {/* Public guest booking flow — no auth required */}
            <Route path="/book" element={<BookPage />} />
            <Route path="/book/success" element={<BookSuccessPage />} />
            <Route path="/book/confirm" element={<BookConfirmPage />} />

            {/* Mobile App Routes — field agents only; anyone else bounces to /dashboard, unauthenticated to /login */}
            <Route element={<ProtectedRoute roles={['field_team']} />}>
              <Route path="/mobile" element={<FieldLayout />}>
                <Route index element={<Navigate to="/mobile/jobs" replace />} />
                <Route path="jobs" element={<MobileJobsPage />} />
                <Route path="map" element={<div className="p-4 text-white">Map View Coming Soon</div>} />
                <Route path="profile" element={<div className="p-4 text-white">Profile Coming Soon</div>} />
              </Route>
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
        <RequestActivityIndicator />
      </BrowserRouter>
      <Toaster />
    </WebSocketProvider>
  );
}

export default App;
