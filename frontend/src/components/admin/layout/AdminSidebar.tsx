import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { LayoutDashboard, Network, Upload, BarChart3, Target, PenSquare, type LucideIcon } from 'lucide-react';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

const navItems: NavItem[] = [
  {
    to: '/admin/overview',
    label: 'Overview',
    icon: LayoutDashboard,
  },
  {
    to: '/admin/ontology',
    label: 'Ontology',
    icon: Network,
  },
  {
    to: '/admin/ingest',
    label: 'Ingest',
    icon: Upload,
  },
  {
    to: '/admin/analytics',
    label: 'Analytics',
    icon: BarChart3,
  },
  {
    to: '/admin/skill-gap',
    label: 'Skill Gap',
    icon: Target,
  },
  {
    to: '/admin/graph-edit',
    label: 'Graph Edit',
    icon: PenSquare,
  },
];

export function AdminSidebar() {
  return (
    <aside className="flex w-64 flex-col border-r border-border bg-muted/30">
      <nav role="navigation" aria-label="Admin navigation" className="flex-1 space-y-1 p-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )
            }
          >
            <item.icon className="h-5 w-5" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
