export interface Customer {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  address: {
    street: string;
    city: string;
    zip: string;
  };
  tags: string[];         // e.g. ["VIP", "Bad Payer"]
  totalSpend: number;     // calculated from completed jobs
  lastServiceDate?: string; 
}
