import { useEffect, useState } from 'react';
import api from '@/lib/axios';
import { CustomerDataTable } from '../components/CustomerDataTable';
import { AddCustomerSheet } from '../components/AddCustomerSheet';
import type { Customer } from '../types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Search, Plus } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [isAddOpen, setIsAddOpen] = useState(false);

  useEffect(() => {
    const fetchCustomers = async () => {
        try {
            const res = await api.get('/api/v1/customers');
            setCustomers(res.data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };
    fetchCustomers();
  }, []);

  const filteredCustomers = customers.filter(c => 
    c.firstName.toLowerCase().includes(search.toLowerCase()) || 
    c.lastName.toLowerCase().includes(search.toLowerCase()) ||
    c.email.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 space-y-6 bg-slate-50">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-heading text-slate-900">Client Directory</h1>
                <p className="text-slate-500">Manage your customer base and view history.</p>
            </div>
            <div className="relative w-full md:w-72">
                <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                <Input 
                    placeholder="Search clients..." 
                    className="pl-9 bg-white border-slate-200"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
            </div>
            <Button onClick={() => setIsAddOpen(true)} className="bg-violet-600 hover:bg-violet-700">
                <Plus className="mr-2 h-4 w-4" /> Add Customer
            </Button>
        </div>

        {loading ? (
            <div className="space-y-4">
                <Skeleton className="h-12 w-full rounded-xl" />
                <Skeleton className="h-12 w-full rounded-xl" />
                <Skeleton className="h-12 w-full rounded-xl" />
            </div>
        ) : (
            <CustomerDataTable data={filteredCustomers} />
        )}

        <AddCustomerSheet 
            open={isAddOpen} 
            onOpenChange={setIsAddOpen} 
            onCustomerCreated={() => window.location.reload()} 
        />
    </div>
  );
}
