import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { format } from 'date-fns';
import { CalendarIcon, Loader2 } from 'lucide-react';
import api from '@/lib/axios';
import { cn } from '@/lib/utils';
import { type CreateJobFormData, createJobSchema } from '../schemas';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Calendar } from '@/components/ui/calendar';
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

interface Provider { id: string; business_name: string; }
interface Service { id: string; name: string; base_price_cents: number; duration_minutes: number; }

interface CreateJobSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onJobCreated: () => void;
}

export function CreateJobSheet({ open, onOpenChange, onJobCreated }: CreateJobSheetProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [error, setError] = useState<string | null>(null);

  const form = useForm<CreateJobFormData>({
    resolver: zodResolver(createJobSchema),
    defaultValues: {
      providerId: '',
      serviceId: '',
      locationPostcode: '',
      locationAddress: '',
      description: '',
      scheduledTime: '',
      basePriceCents: 0,
      durationMinutes: 60,
    },
  });

  const selectedProviderId = form.watch('providerId');

  // Load providers once on mount
  useEffect(() => {
    if (!open) return;
    api.get<Provider[]>('/api/v1/providers/').then(r => setProviders(r.data)).catch(() => {});
  }, [open]);

  // Load services whenever provider changes
  useEffect(() => {
    if (!selectedProviderId) { setServices([]); return; }
    form.setValue('serviceId', '');
    api.get<Service[]>(`/api/v1/providers/${selectedProviderId}/services`)
      .then(r => setServices(r.data))
      .catch(() => setServices([]));
  }, [selectedProviderId, form]);

  const onSubmit = async (data: CreateJobFormData) => {
    setIsSubmitting(true);
    setError(null);
    try {
      const scheduledTime = new Date(
        `${format(data.scheduledDate, 'yyyy-MM-dd')}T${data.scheduledTime}:00`
      ).toISOString();

      await api.post('/api/v1/bookings/', {
        provider_id: data.providerId,
        service_id: data.serviceId,
        scheduled_time: scheduledTime,
        duration_minutes: data.durationMinutes,
        location_postcode: data.locationPostcode,
        location_address: data.locationAddress,
        base_price_cents: data.basePriceCents,
        description: data.description || null,
      });
      form.reset();
      onJobCreated();
      onOpenChange(false);
    } catch {
      setError('Failed to create job. Please check the details and try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[540px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="font-heading text-xl font-bold text-slate-900">Create New Job</SheetTitle>
          <SheetDescription>Select a provider and service, then set the location and time.</SheetDescription>
        </SheetHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 mt-6">

            {/* Provider & Service */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-slate-900 uppercase tracking-wider">Provider & Service</h3>
              <FormField
                control={form.control}
                name="providerId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Provider</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger><SelectValue placeholder="Select a provider" /></SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {providers.map(p => (
                          <SelectItem key={p.id} value={p.id}>{p.business_name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="serviceId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Service</FormLabel>
                    <Select
                      onValueChange={(val) => {
                        field.onChange(val);
                        const svc = services.find(s => s.id === val);
                        if (svc) {
                          form.setValue('basePriceCents', svc.base_price_cents);
                          form.setValue('durationMinutes', svc.duration_minutes);
                        }
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
                )}
              />
            </div>

            {/* Location */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-slate-900 uppercase tracking-wider">Location</h3>
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="locationPostcode"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Postcode</FormLabel>
                      <FormControl><Input placeholder="SW1A 1AA" {...field} /></FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="locationAddress"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Address</FormLabel>
                      <FormControl><Input placeholder="10 Downing St" {...field} /></FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            {/* Schedule */}
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-slate-900 uppercase tracking-wider">Schedule</h3>
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="scheduledDate"
                  render={({ field }) => (
                    <FormItem className="flex flex-col">
                      <FormLabel>Date</FormLabel>
                      <Popover>
                        <PopoverTrigger asChild>
                          <FormControl>
                            <Button variant="outline" className={cn('w-full pl-3 text-left font-normal', !field.value && 'text-muted-foreground')}>
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
                  )}
                />
                <FormField
                  control={form.control}
                  name="scheduledTime"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Time</FormLabel>
                      <FormControl><Input type="time" {...field} /></FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            {/* Notes */}
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Notes (optional)</FormLabel>
                  <FormControl>
                    <Textarea placeholder="Describe the issue or special instructions…" className="resize-none" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {error && <p className="text-sm text-red-500">{error}</p>}

            <SheetFooter>
              <Button
                type="submit"
                disabled={isSubmitting}
                className="w-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-700 hover:to-indigo-700"
              >
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Create Job
              </Button>
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}
