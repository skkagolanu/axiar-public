export type UserRole = 'provider' | 'field_team' | 'admin';

export interface User {
  id: string;
  email: string;
  fullName: string;
  role: UserRole;
  companyName?: string;
  status: 'active' | 'suspended';
}

export interface AuthResponse {
  token: string;
  user: User;
}
