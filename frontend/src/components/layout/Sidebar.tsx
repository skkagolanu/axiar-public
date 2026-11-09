import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  Briefcase,
  Calendar,
  Users,
  Building2,
  FileText,
  Sparkles,
} from 'lucide-react';
// logo import removed

const navItems = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Virtual COO', href: '/dashboard/assistant', icon: Sparkles },
  { name: 'Jobs', href: '/dashboard/jobs', icon: Briefcase },
  { name: 'Schedule', href: '/dashboard/schedule', icon: Calendar },
  { name: 'Live Map', href: '/dashboard/team', icon: Users },
  { name: 'Customers', href: '/dashboard/customers', icon: Building2 },
  { name: 'Reports', href: '/dashboard/reports', icon: FileText },
];

export function Sidebar() {
  const location = useLocation();

  return (
    <div className="hidden h-screen w-64 flex-col bg-secondary text-white lg:flex border-r border-slate-800">
      {/* Brand Area */}
      <div className="flex h-16 items-center gap-3 px-6 border-b border-slate-800">
        {/* <img src={logo} alt="Axiar" className="h-8 w-auto invert brightness-200" /> */}
        <span className="font-heading text-xl font-bold tracking-tight text-white">Axiar</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const isActive = location.pathname === item.href;
          return (
            <Link
              key={item.name}
              to={item.href}
              className={cn(
                'group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'  // Electric Violet for active
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              )}
            >
              <item.icon
                className={cn(
                  'h-5 w-5 flex-shrink-0',
                  isActive ? 'text-primary' : 'text-slate-400 group-hover:text-white'
                )}
              />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Footer / Context */}
      <div className="border-t border-slate-800 p-4">
        <div className="rounded-lg bg-slate-900/50 p-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Workspace</p>
          <p className="mt-1 font-heading text-sm font-bold text-white">Acme Services Co.</p>
        </div>
      </div>
    </div>
  );
}
