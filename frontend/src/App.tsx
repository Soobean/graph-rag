import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SplitView } from '@/components/layout/SplitView';
import { ChatPanel } from '@/components/chat';
import { GraphViewer } from '@/components/graph';
import { ThinkingPanel } from '@/components/thinking';
import { useChatStore, useUiStore } from '@/stores';
import { useHealth } from '@/api/hooks';
import { Activity, AlertCircle } from 'lucide-react';

function App() {
  const { activeRightTab, setActiveRightTab } = useUiStore();
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
        <div className="flex items-center gap-2">
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

export default App;
