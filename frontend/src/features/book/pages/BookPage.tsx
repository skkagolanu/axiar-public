import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { format } from 'date-fns';
import { CalendarIcon, ChevronRight, CreditCard, Loader2 } from 'lucide-react';
import { loadStripe } from '@stripe/stripe-js';
import { Elements, CardElement, useStripe, useElements } from '@stripe/react-stripe-js';
import api from '@/lib/axios';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Calendar } from '@/components/ui/calendar';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { toast } from '@/hooks/use-toast';
import { guestBookingSchema, type GuestBookingFormData } from '../schemas';

// ── Stripe setup ────────────────────────────────────────────────────────────

const stripeKey = import.meta.env.VITE_STRIPE_PUBLIC_KEY;
// Hosted demo: payments are simulated server-side (DEMO_MODE) — no Stripe key,
// no stripe.js, no real card. The backend's /payments/demo-confirm replays the
// production webhook success path instead.
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';
const stripePromise = !DEMO_MODE && stripeKey ? loadStripe(stripeKey) : Promise.resolve(null);

const cardElementOptions = {
  style: {
    base: {
      fontSize: '16px',
      color: '#0f172a',
      '::placeholder': { color: '#94a3b8' },
    },
    invalid: { color: '#dc2626' },
  },
};

interface Provider { id: string; business_name: string; }
interface Service { id: string; name: string; base_price_cents: number; duration_minutes: number; }

const STEPS = ['Provider & Service', 'Your Details', 'Location & Time', 'Payment'] as const;

function BookPageContent() {
  const navigate = useNavigate();
  const stripe = useStripe();
  const elements = useElements();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [services, setServices] = useState<Service[]>([]);

  const form = useForm<GuestBookingFormData>({
    resolver: zodResolver(guestBookingSchema),
    defaultValues: {
      email: '', firstName: '', lastName: '', phone: '',
      providerId: '', serviceId: '',
      locationPostcode: '', locationAddress: '', description: '',
      scheduledTime: '',
      basePriceCents: 0, durationMinutes: 60,
    },
  });

  const [selectedProviderId, selectedServiceId, selectedDate, selectedTime] = useWatch({
    control: form.control,
    name: ['providerId', 'serviceId', 'scheduledDate', 'scheduledTime'],
  });

  const selectedService = useMemo(
    () => services.find(s => s.id === selectedServiceId),
    [services, selectedServiceId]
  );

  useEffect(() => {
    api.get<Provider[]>('/api/v1/providers/').then(r => setProviders(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadServices = async () => {
      form.setValue('serviceId', '');
      if (!selectedProviderId) {
        if (!cancelled) setServices([]);
        return;
      }
      try {
        const { data } = await api.get<Service[]>(`/api/v1/providers/${selectedProviderId}/services`);
        if (!cancelled) setServices(data);
      } catch {
        if (!cancelled) setServices([]);
      }
    };

    loadServices();
    return () => { cancelled = true; };
  }, [selectedProviderId, form]);

  const advanceStep = async () => {
    const stepFields: (keyof GuestBookingFormData)[][] = [
      ['providerId', 'serviceId'],
      ['email', 'firstName', 'lastName'],
      ['locationPostcode', 'locationAddress', 'scheduledDate', 'scheduledTime'],
    ];
    const valid = await form.trigger(stepFields[step]);
    if (valid) setStep(s => s + 1);
  };

  const onSubmit = async (data: GuestBookingFormData) => {
    if (step < STEPS.length - 1) {
      await advanceStep();
      return;
    }

    if (submitting) return; // a re-entrant submit would create a second booking + payment intent

    if (!DEMO_MODE && (!stripe || !elements)) {
      toast({
        variant: 'destructive',
        title: 'Payment unavailable',
        description: 'Stripe has not loaded. Please refresh the page or check your configuration.',
      });
      return;
    }

    const cardElement = DEMO_MODE ? null : elements?.getElement(CardElement);
    if (!DEMO_MODE && !cardElement) {
      toast({
        variant: 'destructive',
        title: 'Payment unavailable',
        description: 'Card details are not ready. Please try again.',
      });
      return;
    }

    setSubmitting(true);
    try {
      const scheduledTime = new Date(
        `${format(data.scheduledDate, 'yyyy-MM-dd')}T${data.scheduledTime}:00`
      ).toISOString();

      const { data: booking } = await api.post<{ id: string; guest_token?: string }>('/api/v1/bookings/guest', {
        email: data.email,
        first_name: data.firstName,
        last_name: data.lastName,
        phone: data.phone || null,
        booking_data: {
          provider_id: data.providerId,
          service_id: data.serviceId,
          scheduled_time: scheduledTime,
          duration_minutes: data.durationMinutes,
          location_postcode: data.locationPostcode,
          location_address: data.locationAddress,
          base_price_cents: data.basePriceCents,
          description: data.description || null,
        },
      });

      // Guest users have no JWT — the guest_token is a short-lived JWT scoped to
      // this booking for the payment-intent call.
      const guestToken = booking.guest_token;
      const intentHeaders: Record<string, string> = {};
      if (guestToken) {
        intentHeaders['X-Guest-Token'] = guestToken;
      }

      const { data: intent } = await api.post<{ client_secret: string; payment_id: string }>('/api/v1/payments/create-intent', {
        booking_id: booking.id,
        amount_cents: data.basePriceCents,
      }, { headers: intentHeaders });

      if (DEMO_MODE) {
        // Simulated payment: the backend replays its webhook success path.
        await api.post('/api/v1/payments/demo-confirm', {
          booking_id: booking.id,
          payment_id: intent.payment_id,
        }, { headers: intentHeaders });
      } else {
        const { error, paymentIntent } = await stripe!.confirmCardPayment(intent.client_secret, {
          payment_method: { card: cardElement! },
        });

        if (error) {
          throw new Error(error.message ?? 'Payment failed');
        }

        if (paymentIntent?.status !== 'succeeded') {
          throw new Error('Payment was not completed. Please try again.');
        }
      }

      navigate('/book/success');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Please check your details and try again.';
      toast({ variant: 'destructive', title: 'Booking failed', description: message });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 py-12 px-4">
      <div className="mx-auto max-w-lg">
        {/* Brand header */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 text-white text-xl font-bold">A</div>
          <h1 className="font-heading text-2xl font-bold text-slate-900">Book a service</h1>
          <p className="mt-1 text-sm text-slate-500">No account needed — we'll email you a confirmation link.</p>
        </div>

        {/* Step indicator */}
        <div className="mb-6 flex items-center gap-2">
          {STEPS.map((label, i) => (
            <div key={label} className="flex flex-1 items-center gap-2">
              <div className={cn(
                'flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold',
                i < step ? 'bg-violet-600 text-white' : i === step ? 'border-2 border-violet-600 text-violet-600' : 'border-2 border-slate-200 text-slate-400'
              )}>
                {i < step ? '✓' : i + 1}
              </div>
              <span className={cn('text-xs hidden sm:block', i === step ? 'text-slate-900 font-medium' : 'text-slate-400')}>{label}</span>
              {i < STEPS.length - 1 && <div className="flex-1 border-t border-slate-200" />}
            </div>
          ))}
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">

              {/* Step 0 — Provider & Service */}
              {step === 0 && (
                <>
                  <h2 className="font-heading text-lg font-bold text-slate-900">Choose a provider &amp; service</h2>
                  <FormField control={form.control} name="providerId" render={({ field }) => (
                    <FormItem>
                      <FormLabel>Provider</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl><SelectTrigger><SelectValue placeholder="Select a provider" /></SelectTrigger></FormControl>
                        <SelectContent>
                          {providers.map(p => <SelectItem key={p.id} value={p.id}>{p.business_name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )} />
                  <FormField control={form.control} name="serviceId" render={({ field }) => (
                    <FormItem>
                      <FormLabel>Service</FormLabel>
                      <Select
                        onValueChange={val => {
                          field.onChange(val);
                          const svc = services.find(s => s.id === val);
                          if (svc) { form.setValue('basePriceCents', svc.base_price_cents); form.setValue('durationMinutes', svc.duration_minutes); }
                        }}
                        value={field.value}
                        disabled={!selectedProviderId || services.length === 0}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder={selectedProviderId ? 'Select a service' : 'Select a provider first'} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {services.map(s => (
                            <SelectItem key={s.id} value={s.id}>
                              {s.name} — £{(s.base_price_cents / 100).toFixed(2)} · {s.duration_minutes} min
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )} />
                </>
              )}

              {/* Step 1 — Contact */}
              {step === 1 && (
                <>
                  <h2 className="font-heading text-lg font-bold text-slate-900">Your details</h2>
                  <div className="grid grid-cols-2 gap-4">
                    <FormField control={form.control} name="firstName" render={({ field }) => (
                      <FormItem><FormLabel>First name</FormLabel><FormControl><Input placeholder="Jane" {...field} /></FormControl><FormMessage /></FormItem>
                    )} />
                    <FormField control={form.control} name="lastName" render={({ field }) => (
                      <FormItem><FormLabel>Last name</FormLabel><FormControl><Input placeholder="Smith" {...field} /></FormControl><FormMessage /></FormItem>
                    )} />
                  </div>
                  <FormField control={form.control} name="email" render={({ field }) => (
                    <FormItem><FormLabel>Email</FormLabel><FormControl><Input type="email" placeholder="jane@example.com" {...field} /></FormControl><FormMessage /></FormItem>
                  )} />
                  <FormField control={form.control} name="phone" render={({ field }) => (
                    <FormItem><FormLabel>Phone (optional)</FormLabel><FormControl><Input type="tel" placeholder="+44 7700 900000" {...field} /></FormControl><FormMessage /></FormItem>
                  )} />
                </>
              )}

              {/* Step 2 — Location & Schedule */}
              {step === 2 && (
                <>
                  <h2 className="font-heading text-lg font-bold text-slate-900">Location &amp; time</h2>
                  <div className="grid grid-cols-2 gap-4">
                    <FormField control={form.control} name="locationPostcode" render={({ field }) => (
                      <FormItem><FormLabel>Postcode</FormLabel><FormControl><Input placeholder="SW1A 1AA" {...field} /></FormControl><FormMessage /></FormItem>
                    )} />
                    <FormField control={form.control} name="locationAddress" render={({ field }) => (
                      <FormItem><FormLabel>Address</FormLabel><FormControl><Input placeholder="10 Downing St" {...field} /></FormControl><FormMessage /></FormItem>
                    )} />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <FormField control={form.control} name="scheduledDate" render={({ field }) => (
                      <FormItem className="flex flex-col">
                        <FormLabel>Date</FormLabel>
                        <Popover>
                          <PopoverTrigger asChild>
                            <FormControl>
                              <Button data-testid="book-date-trigger" variant="outline" className={cn('w-full pl-3 text-left font-normal', !field.value && 'text-muted-foreground')}>
                                {field.value ? format(field.value, 'PPP') : <span>Pick a date</span>}
                                <CalendarIcon className="ml-auto h-4 w-4 opacity-50" />
                              </Button>
                            </FormControl>
                          </PopoverTrigger>
                          <PopoverContent className="w-auto p-0" align="start">
                            <Calendar
                              mode="single"
                              selected={field.value}
                              onSelect={field.onChange}
                              disabled={(date: Date) => date < new Date(new Date().setHours(0, 0, 0, 0))}
                              initialFocus
                            />
                          </PopoverContent>
                        </Popover>
                        <FormMessage />
                      </FormItem>
                    )} />
                    <FormField control={form.control} name="scheduledTime" render={({ field }) => (
                      <FormItem><FormLabel>Time</FormLabel><FormControl><Input type="time" {...field} /></FormControl><FormMessage /></FormItem>
                    )} />
                  </div>
                  <FormField control={form.control} name="description" render={({ field }) => (
                    <FormItem>
                      <FormLabel>Notes (optional)</FormLabel>
                      <FormControl><Textarea placeholder="Describe the issue or special instructions…" className="resize-none" {...field} /></FormControl>
                      <FormMessage />
                    </FormItem>
                  )} />
                </>
              )}

              {/* Step 3 — Secure payment */}
              {step === 3 && (
                <>
                  <h2 className="font-heading text-lg font-bold text-slate-900">Payment</h2>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                    <div className="flex justify-between py-1">
                      <span className="text-slate-500">Service</span>
                      <span className="font-medium">{selectedService?.name ?? '—'}</span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-slate-500">Date &amp; time</span>
                      <span className="font-medium">
                        {selectedDate && selectedTime
                          ? `${format(selectedDate, 'PPP')} at ${selectedTime}`
                          : '—'}
                      </span>
                    </div>
                    <div className="mt-2 flex justify-between border-t border-slate-200 pt-2">
                      <span className="text-slate-500">Total</span>
                      <span className="font-bold text-slate-900">
                        {selectedService ? `£${(selectedService.base_price_cents / 100).toFixed(2)}` : '—'}
                      </span>
                    </div>
                  </div>

                  {DEMO_MODE ? (
                    <div className="rounded-md border border-violet-200 bg-violet-50 px-3 py-3 text-sm text-violet-800">
                      <span className="font-medium">Demo mode</span> — no real payment is taken.
                      Confirming simulates a successful card payment.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Label className="flex items-center gap-2">
                        <CreditCard className="h-4 w-4" />
                        Card details
                      </Label>
                      <div className="rounded-md border border-slate-200 bg-white px-3 py-3 shadow-sm focus-within:border-violet-600 focus-within:ring-1 focus-within:ring-violet-600">
                        <CardElement options={cardElementOptions} />
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Navigation */}
              <div className="flex gap-3 pt-2">
                {step > 0 && (
                  <Button type="button" variant="outline" onClick={() => setStep(s => s - 1)} className="flex-1">
                    Back
                  </Button>
                )}
                {step < STEPS.length - 1 ? (
                  // key: without it React reuses this DOM node for the submit button below
                  // when step becomes 3, and the browser evaluates the click's default
                  // action against the mutated type="submit" — submitting the whole form
                  // (booking + payment) from the step-2 "Next" click.
                  <Button key="step-next" type="button" onClick={advanceStep} className="flex-1 bg-gradient-to-r from-violet-600 to-indigo-600 text-white">
                    Next <ChevronRight className="ml-1 h-4 w-4" />
                  </Button>
                ) : (
                  <Button key="step-submit" type="submit" disabled={submitting || (!DEMO_MODE && !stripe)} className="flex-1 bg-gradient-to-r from-violet-600 to-indigo-600 text-white">
                    {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {submitting ? 'Processing…' : 'Confirm & pay'}
                  </Button>
                )}
              </div>
            </form>
          </Form>
        </div>
      </div>
    </div>
  );
}

export default function BookPage() {
  return (
    <Elements stripe={stripePromise}>
      <BookPageContent />
    </Elements>
  );
}
