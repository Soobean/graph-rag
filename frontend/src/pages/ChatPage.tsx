import { Link } from 'react-router-dom';
import { SplitView } from '@/components/layout/SplitView';
import { ChatPanel } from '@/components/chat';
import { GraphViewer } from '@/components/graph';
import { useUiStore } from '@/stores';
import { useHealth } from '@/api/hooks';
import { Activity, AlertCircle, Columns, Settings, Target, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import type { DemoRole } from '@/stores/uiStore';

const ROLE_STYLES: Record<DemoRole, string> = {
  admin: 'text-red-700 bg-red-50 border-red-200',
  manager: 'text-blue-700 bg-blue-50 border-blue-200',
  editor: 'text-green-700 bg-green-50 border-green-200',
  viewer: 'text-gray-700 bg-gray-50 border-gray-200',
};

export function ChatPage() {
  const { isRightPanelOpen, closeRightPanel, demoRole, setDemoRole } = useUiStore();
  const { data: health, isError } = useHealth();

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <h1 className="text-xl font-bold">Graph RAG Explorer</h1>
        <div className="flex items-center gap-3">
          <Select
            value={demoRole}
            onChange={(e) => setDemoRole(e.target.value as DemoRole)}
            className={`h-8 w-32 text-xs font-medium ${ROLE_STYLES[demoRole]}`}
          >
            <option value="admin">admin</option>
            <option value="manager">manager</option>
            <option value="editor">editor</option>
            <option value="viewer">viewer</option>
          </Select>
          {isError ? (
            <div className="flex items-center gap-1 text-destructive">
              <AlertCircle className="h-4 w-4" />
              <span className="text-sm">API Disconnected</span>
            </div>
          ) : health ? (
            <div className="flex items-center gap-1 text-green-600">
              <Activity className="h-4 w-4" />
              <span className="text-sm">Connected</span>
            </div>
          ) : null}
          <Link to="/compare">
            <Button variant="outline" size="sm">
              <Columns className="mr-1 h-4 w-4" />
              Compare
            </Button>
          </Link>
          <Link to="/staffing">
            <Button variant="outline" size="sm">
              <Target className="mr-1 h-4 w-4" />
              Staffing
            </Button>
          </Link>
          <Link to="/admin">
            <Button variant="outline" size="sm">
              <Settings className="mr-1 h-4 w-4" />
              Admin
            </Button>
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden">
        <SplitView
          rightCollapsed={!isRightPanelOpen}
          leftPanel={<ChatPanel className="bg-white" />}
          rightPanel={
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b border-border px-4 py-2">
                <span className="text-sm font-medium">Graph</span>
                <Button variant="ghost" size="icon" onClick={closeRightPanel} title="패널 닫기">
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <div className="flex-1 min-h-0">
                <GraphViewer className="h-full" />
              </div>
            </div>
          }
        />
      </main>
    </div>
  );
}
