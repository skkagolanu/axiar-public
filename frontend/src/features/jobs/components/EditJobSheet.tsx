import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Calendar } from '@/components/ui/calendar';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { CalendarIcon, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';
import api from '@/lib/axios';
import { useState, useEffect } from 'react';
import type { Job } from '../types';

// Local schema — EditJobSheet only edits a subset of fields (customer/service type
// are read-only display, not part of BookingUpdate); keep it independent from
// createJobSchema (A2b) which models the create-flow's provider/service selection.
const editJobSchema = z.object({
  customerName: z.string(),
  customerPhone: z.string(),
  address: z.string().min(5, 'Address is required'),
  description: z.string().optional(),
  priority: z.string(),
  serviceType: z.string(),
  scheduledDate: z.date({ message: 'Date is required' }),
  scheduledTime: z.string().min(1, 'Time is required'),
});

type EditJobFormData = z.infer<typeof editJobSchema>;

interface EditJobSheetProps {
  job: Job | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onJobUpdated: () => void;
}

export function EditJobSheet({ job, open, onOpenChange, onJobUpdated }: EditJobSheetProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const form = useForm<EditJobFormData>({
    resolver: zodResolver(editJobSchema),
    defaultValues: {
      customerName: '',
      customerPhone: '',
      address: '',
      description: '',
      priority: 'medium',
      serviceType: '',
      scheduledTime: '',
      scheduledDate: new Date(),
    },
  });

  // Reset form when job changes
  useEffect(() => {
    if (job) {
      form.reset({
        customerName: job.customerName,
        customerPhone: job.customerPhone,
        address: job.address,
        description: job.description,
        priority: job.priority as any,
        serviceType: job.serviceType,
        scheduledTime: job.scheduledTime,
        scheduledDate: new Date(job.scheduledDate),
      });
    }
  }, [job, form]);

  const onSubmit = async (data: EditJobFormData) => {
    if (!job) return;
    setIsSubmitting(true);
    try {
      const payload = {
        description: data.description,
        scheduled_time: data.scheduledDate instanceof Date
            ? new Date(data.scheduledDate.toISOString().split('T')[0] + 'T' + data.scheduledTime).toISOString()
            : new Date(data.scheduledDate + 'T' + data.scheduledTime).toISOString(),
        location_address: data.address,
        // Booking updates use the fields supported by the API schema.
        // dispatch.py create job handles priority but Booking model doesn't seem to store it explicitly besides logic?
        // Actually Booking model (Step 218) does NOT have priority column. It uses Logic or Tags?
    
      };
      
      await api.patch(`/bookings/${job.id}`, payload);
      onJobUpdated();
      onOpenChange(false);
    } catch (error) {
      console.error('Failed to update job', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-[540px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="font-heading text-xl font-bold text-slate-900">Edit Job</SheetTitle>
          <SheetDescription>
            Update job details below.
          </SheetDescription>
        </SheetHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 mt-6">
            
            {/* Customer identity is managed separately from booking details. */}
             <div className="space-y-4">
                <h3 className="text-sm font-semibold text-slate-900 uppercase tracking-wider">Customer Info</h3>
                <div className="grid grid-cols-2 gap-4">
                    <FormField
                    control={form.control}
                    name="customerName"
                    render={({ field }) => (
                        <FormItem>
                        <FormLabel>Name</FormLabel>
                        <FormControl>
                            <Input {...field} disabled />
                        </FormControl>
                        <FormMessage />
                        </FormItem>
                    )}
                    />
                     <FormField
                    control={form.control}
                    name="customerPhone"
                    render={({ field }) => (
                        <FormItem>
                        <FormLabel>Phone</FormLabel>
                        <FormControl>
                            <Input {...field} disabled />
                        </FormControl>
                        <FormMessage />
                        </FormItem>
                    )}
                    />
                </div>
                 <FormField
                    control={form.control}
                    name="address"
                    render={({ field }) => (
                        <FormItem>
                        <FormLabel>Address</FormLabel>
                        <FormControl>
                            <Input {...field} />
                        </FormControl>
                        <FormMessage />
                        </FormItem>
                    )}
                />
            </div>

            {/* Job Details Section */}
             <div className="space-y-4">
                <h3 className="text-sm font-semibold text-slate-900 uppercase tracking-wider">Job Details</h3>
                
                {/* Service Type - Disabled/Readonly usually, but let's allow edit if desired */}
                <FormField
                    control={form.control}
                    name="serviceType"
                    render={({ field }) => (
                        <FormItem>
                        <FormLabel>Service Type</FormLabel>
                        <FormControl>
                            <Input {...field} disabled />
                        </FormControl>
                        <FormMessage />
                        </FormItem>
                    )}
                    />

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
                                    <Button
                                    variant={"outline"}
                                    className={cn(
                                        "w-full pl-3 text-left font-normal",
                                        !field.value && "text-muted-foreground"
                                    )}
                                    >
                                    {field.value ? (
                                        format(field.value, "PPP")
                                    ) : (
                                        <span>Pick a date</span>
                                    )}
                                    <CalendarIcon className="ml-auto h-4 w-4 opacity-50" />
                                    </Button>
                                </FormControl>
                                </PopoverTrigger>
                                <PopoverContent className="w-auto p-0" align="start">
                                <Calendar
                                    mode="single"
                                    selected={field.value}
                                    onSelect={field.onChange}
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
                            <FormControl>
                                <Input type="time" {...field} />
                            </FormControl>
                            <FormMessage />
                            </FormItem>
                        )}
                        />
                </div>

                <FormField
                    control={form.control}
                    name="description"
                    render={({ field }) => (
                        <FormItem>
                        <FormLabel>Description</FormLabel>
                        <FormControl>
                            <Textarea 
                                className="resize-none"
                                {...field} 
                            />
                        </FormControl>
                        <FormMessage />
                        </FormItem>
                    )}
                />
            </div>


            <SheetFooter>
              <Button type="submit" disabled={isSubmitting} className="w-full bg-violet-600 hover:bg-violet-700">
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save Changes
              </Button>
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}
