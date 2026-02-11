import { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import { ChatPage } from '@/pages/ChatPage';
import { Loader2 } from 'lucide-react';

// Lazy load admin components
const AdminLayout = lazy(() =>
  import('@/components/admin/layout/AdminLayout').then((m) => ({ default: m.AdminLayout }))
);
const OverviewPage = lazy(() =>
  import('@/pages/admin/OverviewPage').then((m) => ({ default: m.OverviewPage }))
);
const OntologyPage = lazy(() =>
  import('@/pages/admin/OntologyPage').then((m) => ({ default: m.OntologyPage }))
);
const IngestPage = lazy(() =>
  import('@/pages/admin/IngestPage').then((m) => ({ default: m.IngestPage }))
);
const AnalyticsPage = lazy(() =>
  import('@/pages/admin/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage }))
);
const SkillGapPage = lazy(() =>
  import('@/pages/SkillGapPage').then((m) => ({ default: m.SkillGapPage }))
);
const GraphEditPage = lazy(() =>
  import('@/pages/admin/GraphEditPage').then((m) => ({ default: m.GraphEditPage }))
);
const ComparePage = lazy(() =>
  import('@/pages/ComparePage').then((m) => ({ default: m.ComparePage }))
);

// eslint-disable-next-line react-refresh/only-export-components
function PageLoader() {
  return (
    <div className="flex h-full items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
function SuspenseWrapper({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<PageLoader />}>{children}</Suspense>;
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <ChatPage />,
  },
  {
    path: '/compare',
    element: (
      <SuspenseWrapper>
        <ComparePage />
      </SuspenseWrapper>
    ),
  },
  {
    path: '/skill-gap',
    element: (
      <SuspenseWrapper>
        <SkillGapPage />
      </SuspenseWrapper>
    ),
  },
  {
    path: '/admin',
    element: (
      <SuspenseWrapper>
        <AdminLayout />
      </SuspenseWrapper>
    ),
    children: [
      {
        index: true,
        element: <Navigate to="/admin/overview" replace />,
      },
      {
        path: 'overview',
        element: (
          <SuspenseWrapper>
            <OverviewPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'ontology',
        element: (
          <SuspenseWrapper>
            <OntologyPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'ingest',
        element: (
          <SuspenseWrapper>
            <IngestPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'analytics',
        element: (
          <SuspenseWrapper>
            <AnalyticsPage />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'graph-edit',
        element: (
          <SuspenseWrapper>
            <GraphEditPage />
          </SuspenseWrapper>
        ),
      },
    ],
  },
]);
