import { Link } from "react-router-dom";
import { SplitView } from "@/components/layout/SplitView";
import { ChatPanel } from "@/components/chat";
import { GraphViewer } from "@/components/graph";
import { useUiStore } from "@/stores";
import { useHealth } from "@/api/hooks";
import { AlertCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import LOGO from "@/assets/img/LOGO.png";
import type { DemoRole } from "@/stores/uiStore";
import SETTING from "@/assets/svg/SETTING.svg";
import USERS from "@/assets/svg/USERS.svg";
import COMPARE from "@/assets/svg/COMPARE.svg";
import { NavSelect } from "@/components/ui/nav-select";

// const ROLE_STYLES: Record<DemoRole, string> = {
//   admin: "text-red-700 bg-red-50 border-red-200",
//   manager: "text-blue-700 bg-blue-50 border-blue-200",
//   editor: "text-green-700 bg-green-50 border-green-200",
//   viewer: "text-gray-700 bg-gray-50 border-gray-200",
// };

export function ChatPage() {
  const { isRightPanelOpen, closeRightPanel, demoRole, setDemoRole } =
    useUiStore();
  const { data: health, isError } = useHealth();

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border pl-4 pr-2">
        <img src={LOGO} alt="Logo" className="h-6 w-auto" />
        <div className="flex items-center gap-3">
          {isError ? (
            <div className="flex items-center gap-2 bg-red-50 text-destructive border border-red-300 px-3 py-1 rounded-md">
              <AlertCircle className="h-4 w-4" />
              <span className="text-sm">API Disconnected</span>
            </div>
          ) : health ? (
            <div className="flex items-center gap-2 bg-green-50 text-success border border-green-300 px-3 py-1 rounded-md">
              <div className="w-2 h-2 bg-success rounded-full mr-1 shadow-[0_0_6px_0_hsl(var(--success-green))]"></div>
              <span className="text-sm">Connected</span>
            </div>
          ) : null}

          <Link to="/compare">
            <Button variant="ghost" size="sm">
              <img src={COMPARE} alt="Compare" className="mr-1 h-4 w-4" />
              Compare
            </Button>
          </Link>
          <Link to="/staffing">
            <Button variant="ghost" size="sm">
              <img src={USERS} alt="Staffing" className="mr-1 h-4 w-4" />
              Staffing
            </Button>
          </Link>

          {/* 왼쪽에만 border 들어가도록 */}
          <div className="flex items-center gap-2">
            <div className="w-1 h-5 border-l border-border pl-2"></div>
            <NavSelect
              value={demoRole}
              onChange={(e) => setDemoRole(e.target.value as DemoRole)}
              className={`h-8 w-32 text-xs font-medium`}
            >
              <option value="admin">admin</option>
              <option value="manager">manager</option>
              <option value="editor">editor</option>
              <option value="viewer">viewer</option>
            </NavSelect>
            <Link to="/admin">
              <Button variant="ghost" size="sm">
                {/* <Settings className="mr-1 h-4 w-4" /> */}
                <img src={SETTING} alt="Settings" className="h-6 w-6" />
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden">
        <SplitView
          rightCollapsed={!isRightPanelOpen}
          leftPanel={<ChatPanel className="bg-white" />}
          rightPanel={
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <span className="text-sm font-medium">Graph</span>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={closeRightPanel}
                  title="패널 닫기"
                >
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
