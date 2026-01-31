# Graph RAG Frontend

Graph RAG 시스템을 위한 React 기반 웹 프론트엔드

## 기술 스택

- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **Routing**: React Router v6
- **State Management**: TanStack Query (React Query)
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui 패턴

## 주요 기능

### Chat Interface (`/`)
- 자연어 질의 및 그래프 기반 답변
- SSE 스트리밍 응답 지원
- 추론 과정 시각화 (Explainable AI)
- 그래프 결과 시각화

### Admin Dashboard (`/admin`)

| 섹션 | 경로 | 설명 |
|------|------|------|
| Overview | `/admin/overview` | 시스템 상태, Neo4j 연결, 그래프 통계 |
| Ontology | `/admin/ontology` | 온톨로지 제안 관리 (승인/거절/배치) |
| Ingest | `/admin/ingest` | 데이터 적재 작업 제출 및 모니터링 |
| Analytics | `/admin/analytics` | 커뮤니티 탐지, 유사 직원, 팀 추천 |

## 프로젝트 구조

```
frontend/src/
├── api/
│   ├── client.ts              # Axios 인스턴스
│   └── hooks/
│       ├── useHealth.ts       # 헬스체크 훅
│       ├── useChat.ts         # 채팅 API 훅
│       └── admin/             # Admin API 훅
│           ├── useOntologyAdmin.ts
│           ├── useIngest.ts
│           ├── useAnalytics.ts
│           └── useSchema.ts
├── components/
│   ├── ui/                    # 재사용 UI 컴포넌트
│   │   ├── button.tsx
│   │   ├── badge.tsx
│   │   ├── table.tsx
│   │   ├── dialog.tsx
│   │   ├── select.tsx
│   │   ├── checkbox.tsx
│   │   └── progress.tsx
│   ├── chat/                  # 채팅 컴포넌트
│   └── admin/                 # Admin 컴포넌트
│       ├── layout/            # 레이아웃 (Header, Sidebar)
│       ├── overview/          # Overview 섹션
│       ├── ontology/          # Ontology 섹션
│       ├── ingest/            # Ingest 섹션
│       └── analytics/         # Analytics 섹션
├── pages/
│   ├── ChatPage.tsx           # 채팅 페이지
│   └── admin/                 # Admin 페이지
├── hooks/
│   └── useDebounce.ts         # 디바운스 훅
├── stores/
│   └── uiStore.ts             # Zustand UI 상태
├── types/
│   └── admin.ts               # Admin 타입 정의
├── router.tsx                 # 라우터 설정
└── main.tsx                   # 앱 진입점
```

## 개발 명령어

```bash
# 의존성 설치
npm install

# 개발 서버 실행 (port 3000)
npm run dev

# 프로덕션 빌드
npm run build

# 빌드 미리보기
npm run preview

# 린트
npm run lint
```

## 환경 설정

`.env` 파일 (선택):

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

기본값: `/api/v1` (Vite 프록시 사용)

## 주요 패턴

### API Hooks (TanStack Query)

```typescript
// 조회 (useQuery)
const { data, isLoading, error } = useProposalList({ status: 'pending' });

// 변경 (useMutation)
const { mutate, isPending } = useApproveProposal();
mutate({ proposalId, request });
```

### 코드 스플리팅

```typescript
// React.lazy로 Admin 페이지 지연 로딩
const OverviewPage = lazy(() => import('@/pages/admin/OverviewPage'));
```

### 접근성

- Dialog: Focus trap, ESC 키 핸들링, ARIA 속성
- 시맨틱 HTML 사용
- 키보드 네비게이션 지원

## 백엔드 연동

백엔드 API 서버가 `http://localhost:8000`에서 실행 중이어야 합니다.

```bash
# 루트 디렉토리에서
uvicorn src.main:app --reload
```

## 라이선스

MIT License
