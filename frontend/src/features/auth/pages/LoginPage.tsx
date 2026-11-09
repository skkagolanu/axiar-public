import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate } from 'react-router-dom';
import { loginSchema, type LoginFormData } from '../schemas';
import { useAuthStore } from '@/store/useAuthStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import api from '@/lib/axios';
import { isAxiosError } from 'axios';

export default function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);
  const [error, setError] = useState<string | null>(null);

  const form = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: '',
      password: '',
      rememberMe: false,
    },
  });
  const isSubmitting = form.formState.isSubmitting;

  const onSubmit = async (data: LoginFormData) => {
    setError(null);
    try {
      // Convert to URLSearchParams for OAuth2 password flow
      const formData = new URLSearchParams();
      formData.append('username', data.email);
      formData.append('password', data.password);

      const response = await api.post('/api/v1/auth/login', formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });
      // Backend returns UserLoginResponse: { access_token, user: { first_name, last_name, ... } }
      const { user: backendUser, access_token } = response.data;
      
      // Map backend user to frontend User interface
      const frontendUser = {
        id: backendUser.id,
        email: backendUser.email,
        fullName: `${backendUser.first_name} ${backendUser.last_name}`.trim(),
        role: backendUser.role === 'field_agent' ? 'field_team' : backendUser.role,
        status: (backendUser.is_active ? 'active' : 'suspended') as 'active' | 'suspended',
        companyName: backendUser.business_name,
      };

      setAuth(frontendUser, access_token);
      navigate('/');
    } catch (err) {
      const errorMessage =
        (isAxiosError(err) && err.response?.data?.detail) || 'Invalid credentials. Try again.';
      setError(errorMessage);
      console.error(err);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="text-2xl font-heading">Welcome back</CardTitle>
        <CardDescription>
          Enter your email to sign in to your account
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input placeholder="name@example.com" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Password</FormLabel>
                  <FormControl>
                    <Input type="password" placeholder="••••••••" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="rememberMe"
              render={({ field }) => (
                <FormItem className="flex flex-row items-start space-x-3 space-y-0 text-sm">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <div className="space-y-1 leading-none">
                    <FormLabel>
                      Remember me
                    </FormLabel>
                  </div>
                </FormItem>
              )}
            />
            {error && <div className="text-sm text-red-500">{error}</div>}
            <Button
              type="submit"
              loading={isSubmitting}
              loadingText="Signing in…"
              className="w-full font-bold shadow-lg hover:shadow-primary/25 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white"
            >
              Sign In
            </Button>
            {isSubmitting && (
              <p className="text-center text-xs text-muted-foreground" role="status">
                Connecting to the live demo. A cold start can take up to a minute.
              </p>
            )}
          </form>
        </Form>
        {import.meta.env.VITE_DEMO_MODE === 'true' && (
          <div className="mt-4 rounded-md border border-violet-200 bg-violet-50 p-3 text-sm">
            {/* Use a light palette for the demo account selector. */}
            <p className="mb-2 font-medium text-slate-600">
              Live demo — click to fill (data resets nightly):
            </p>
            {[
              { label: 'Provider', email: 'provider@example.test' },
              { label: 'Customer', email: 'customer@example.test' },
              { label: 'Field agent', email: 'field-agent@example.test' },
            ].map(({ label, email }) => (
              <button
                key={email}
                type="button"
                className="block w-full rounded px-2 py-1 text-left text-slate-600 hover:bg-violet-100 hover:text-slate-900"
                onClick={() => {
                  form.setValue('email', email);
                  form.setValue('password', 'AxiarDemo1');
                }}
              >
                <span className="font-medium">{label}</span> · {email}
              </button>
            ))}
          </div>
        )}
      </CardContent>
      <CardFooter className="flex justify-center">
        <p className="text-sm text-muted-foreground">
          Don't have an account?{' '}
          <Link to="/register" className="text-primary hover:underline">
            Create an account
          </Link>
        </p>
      </CardFooter>
    </Card>
  );
}
