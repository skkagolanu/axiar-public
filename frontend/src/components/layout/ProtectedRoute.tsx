import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/store/useAuthStore';
import type { UserRole } from '@/features/auth/types';

interface ProtectedRouteProps {
  /** When set, only these roles may pass; anyone else is bounced to /dashboard. */
  roles?: UserRole[];
}

export default function ProtectedRoute({ roles }: ProtectedRouteProps = {}) {
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (roles && (!user || !roles.includes(user.role))) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
}
