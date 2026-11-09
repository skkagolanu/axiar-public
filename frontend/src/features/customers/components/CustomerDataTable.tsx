import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import type { Customer } from "../types";

interface CustomerDataTableProps {
  data: Customer[];
}

export function CustomerDataTable({ data }: CustomerDataTableProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      <Table>
        <TableHeader className="bg-slate-50">
          <TableRow>
            <TableHead className="w-[80px]">Initials</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Total Spend</TableHead>
            <TableHead>Last Service</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((customer) => (
            <TableRow key={customer.id} className="hover:bg-slate-50 transition-colors cursor-pointer">
              <TableCell>
                <Avatar className="h-10 w-10 border-2 border-slate-100">
                  <AvatarFallback className="bg-violet-100 text-violet-700 font-bold">
                    {customer.firstName[0]}{customer.lastName[0]}
                  </AvatarFallback>
                </Avatar>
              </TableCell>
              <TableCell>
                <div className="flex flex-col">
                    <span className="font-bold text-slate-900">{customer.firstName} {customer.lastName}</span>
                    <span className="text-xs text-slate-500">{customer.address.city}, {customer.address.zip}</span>
                </div>
              </TableCell>
              <TableCell>
                <div className="flex gap-2">
                    {customer.tags.map(tag => (
                        <Badge key={tag} variant="outline" className={
                            tag === 'VIP' ? 'bg-violet-50 text-violet-700 border-violet-200' :
                            tag === 'Bad Payer' || tag === 'Late Payment' ? 'bg-rose-50 text-rose-700 border-rose-200' :
                            'bg-slate-100 text-slate-600'
                        }>
                            {tag}
                        </Badge>
                    ))}
                </div>
              </TableCell>
              <TableCell>
                <span className="font-mono font-medium text-slate-700">
                    ${customer.totalSpend.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </span>
              </TableCell>
              <TableCell className="text-slate-500 text-sm">
                {customer.lastServiceDate ? new Date(customer.lastServiceDate).toLocaleDateString() : 'N/A'}
              </TableCell>
              <TableCell className="text-right">
                <Button variant="ghost" size="sm" className="text-slate-400 hover:text-violet-600">
                    View Profile
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
