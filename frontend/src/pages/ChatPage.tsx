import { Link } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SplitView } from '@/components/layout/SplitView';
import { ChatPanel } from '@/components/chat';
import { GraphViewer } from '@/components/graph';
import { ThinkingPanel } from '@/components/thinking';
import { useChatStore, useUiStore } from '@/stores';
import { useHealth } from '@/api/hooks';
import { Activity, AlertCircle, Columns, Settings, Target } from 'lucide-react';
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
  const { activeRightTab, setActiveRightTab, demoRole, setDemoRole } = useUiStore();
  const { getCurrentMessages } = useChatStore();
  const { data: health, isError } = useHealth();

  const messages = getCurrentMessages();
  const lastAssistantMessage = [...messages].reverse().find((m) => m.role === 'assistant' && !m.isLoading);
  const thoughtProcess = lastAssistantMessage?.thoughtProcess || null;

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
          <Link to="/skill-gap">
            <Button variant="outline" size="sm">
              <Target className="mr-1 h-4 w-4" />
              Skill Gap
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
          leftPanel={<ChatPanel />}
          rightPanel={
            <div className="flex h-full flex-col">
              <Tabs
                value={activeRightTab}
                onValueChange={(v: string) => setActiveRightTab(v as 'graph' | 'thinking')}
                className="flex h-full flex-col"
              >
                <div className="border-b border-border px-4 py-2">
                  <TabsList>
                    <TabsTrigger value="graph">Graph</TabsTrigger>
                    <TabsTrigger value="thinking">Thinking</TabsTrigger>
                  </TabsList>
                </div>
                <TabsContent value="graph" className="flex-1 m-0 data-[state=inactive]:hidden">
                  <GraphViewer className="h-full" />
                </TabsContent>
                <TabsContent value="thinking" className="flex-1 m-0 overflow-hidden data-[state=inactive]:hidden">
                  <ThinkingPanel thoughtProcess={thoughtProcess} className="h-full" />
                </TabsContent>
              </Tabs>
            </div>
          }
        />
      </main>
    </div>
  );
}
