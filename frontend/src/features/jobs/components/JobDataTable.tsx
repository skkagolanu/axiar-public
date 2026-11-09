import type {
  ColumnDef,
} from '@tanstack/react-table';
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { Job } from '../types';
import { JobStatusBadge } from './JobStatusBadge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { MoreHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { EditJobSheet } from './EditJobSheet';
import { useState, useMemo } from 'react';

interface JobDataTableProps {
  data: Job[];
}

export function JobDataTable({ data }: JobDataTableProps) {
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [isEditOpen, setIsEditOpen] = useState(false);

  const handleEdit = (job: Job) => {
    setSelectedJob(job);
    setIsEditOpen(true);
  };

  const columns = useMemo<ColumnDef<Job>[]>(() => [
    {
      accessorKey: 'id',
      header: 'ID',
      cell: ({ row }) => <span className="font-mono text-xs text-slate-500">{row.getValue('id')}</span>,
    },
    {
      accessorKey: 'customerName',
      header: 'Customer',
      cell: ({ row }) => (
        <div className="flex flex-col">
            <span className="font-medium text-slate-900">{row.getValue('customerName')}</span>
            <span className="text-xs text-slate-500">{row.original.address}</span>
        </div>
      ),
    },
    {
      accessorKey: 'serviceType',
      header: 'Service',
    },
    {
      accessorKey: 'scheduledDate',
      header: 'Date',
      cell: ({ row }) => {
          const date = new Date(row.getValue('scheduledDate'));
          const time = row.original.scheduledTime;
          return (
            <div className="flex flex-col">
              <span className="text-slate-900 font-medium">{date.toLocaleDateString()}</span>
              <span className="text-xs text-slate-500">{time}</span>
            </div>
          )
      }
    },
    {
      accessorKey: 'assignedTech',
      header: 'Tech',
      cell: ({ row }) => {
          const tech = row.original.assignedTech;
          if (!tech) return <span className="text-slate-400 text-xs">-</span>;
          
          return (
              <div className="flex items-center gap-2">
                   <Avatar className="h-6 w-6">
                      <AvatarImage src={tech.avatar} />
                      <AvatarFallback>{tech.name[0]}</AvatarFallback>
                   </Avatar>
                   <span className="text-sm text-slate-700">{tech.name}</span>
              </div>
          )
      }
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => <JobStatusBadge status={row.getValue('status')} />,
    },
    {
      accessorKey: 'price',
      header: 'Price',
      cell: ({ row }) => {
          const amount = parseFloat(row.getValue('price') || '0');
          const formatted = new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
          }).format(amount);
          return <div className="font-medium text-slate-900">{formatted}</div>
      }
    },
    {
      id: 'actions',
      cell: ({ row }) => {
        const job = row.original;
   
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-8 w-8 p-0">
                <span className="sr-only">Open menu</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Actions</DropdownMenuLabel>
              <DropdownMenuItem onClick={() => navigator.clipboard.writeText(job.id)}>
                Copy Job ID
              </DropdownMenuItem>
              <DropdownMenuItem>View Details</DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleEdit(job)}>Edit Job</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ], []);

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <>
      <div className="rounded-md border bg-white shadow-sm">
        <Table>
          <TableHeader className="bg-slate-50">
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  return (
                    <TableHead key={header.id} className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && "selected"}
                  className="hover:bg-slate-50"
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} className="py-3">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center">
                  No results.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <EditJobSheet 
        job={selectedJob} 
        open={isEditOpen} 
        onOpenChange={setIsEditOpen} 
        onJobUpdated={() => window.location.reload()}
      />
    </>
  );
}
