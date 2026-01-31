import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { MessageSquare, User } from 'lucide-react';

export function AdminHeader() {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-background px-6">
      <div className="flex items-center gap-4">
        <Link to="/" className="text-xl font-bold text-primary hover:text-primary/80">
          Graph RAG
        </Link>
        <span className="text-muted-foreground">|</span>
        <span className="text-lg font-medium">Admin Dashboard</span>
      </div>
      <div className="flex items-center gap-2">
        <Link to="/">
          <Button variant="outline" size="sm">
            <MessageSquare className="mr-1 h-4 w-4" />
            Chat
          </Button>
        </Link>
        <Button variant="ghost" size="icon" aria-label="User settings">
          <User className="h-5 w-5" />
          <span className="sr-only">User settings</span>
        </Button>
      </div>
    </header>
  );
}
