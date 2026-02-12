// Ontology Admin Types

export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'auto_approved';
export type ProposalType = 'NEW_CONCEPT' | 'NEW_SYNONYM' | 'NEW_RELATION';
export type ProposalSource = 'chat' | 'background' | 'admin';

export interface Proposal {
  id: string;
  version: number;
  proposal_type: ProposalType;
  term: string;
  category: string;
  suggested_action: string;
  suggested_parent: string | null;
  suggested_canonical: string | null;
  suggested_relation_type: string | null;
  frequency: number;
  confidence: number;
  status: ProposalStatus;
  source: ProposalSource;
  evidence_questions: string[];
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  applied_at: string | null;
}

export interface ProposalDetail extends Proposal {
  all_evidence_questions: string[];
  rejection_reason: string | null;
}

export interface PaginationMeta {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ProposalListResponse {
  items: Proposal[];
  pagination: PaginationMeta;
}

export interface ProposalApproveRequest {
  expected_version: number;
  canonical?: string;
  parent?: string;
  note?: string;
}

export interface ProposalRejectRequest {
  expected_version: number;
  reason: string;
}

export interface BatchOperationResponse {
  success_count: number;
  failed_count: number;
  failed_ids: string[];
  errors: Array<{ id: string; message: string }>;
}

export interface UnresolvedTermStats {
  term: string;
  category: string;
  frequency: number;
  confidence: number;
}

export interface OntologyStats {
  total_proposals: number;
  pending_count: number;
  approved_count: number;
  auto_approved_count: number;
  rejected_count: number;
  category_distribution: Record<string, number>;
  top_unresolved_terms: UnresolvedTermStats[];
}

// Ingest Types

export type IngestJobStatus = 'pending' | 'running' | 'completed' | 'failed';
export type SourceType = 'csv' | 'excel';

export interface IngestRequest {
  file_path: string;
  source_type: SourceType;
  sheet_name?: string;
  header_row?: number;
  batch_size?: number;
  concurrency?: number;
}

export interface IngestStats {
  total_documents: number;
  total_nodes: number;
  total_edges: number;
  failed_documents: number;
  duration_seconds: number;
}

export interface IngestJob {
  job_id: string;
  status: IngestJobStatus;
  progress: number;
  stats: IngestStats;
  error: string | null;
}

export interface IngestResponse {
  success: boolean;
  message: string;
  job_id: string;
  stats: IngestStats;
}

export interface FileUploadResponse {
  success: boolean;
  file_path: string;
  file_name: string;
  file_size: number;
  source_type: SourceType;
}

// Analytics Types

export interface ProjectionStatus {
  exists: boolean;
  name: string;
  node_count: number | null;
  relationship_count: number | null;
  details?: Record<string, unknown>;
}

export interface CommunityInfo {
  community_id: number;
  member_count: number;
  sample_members: string[];
}

export interface CommunityDetectResponse {
  success: boolean;
  algorithm: string;
  community_count: number;
  modularity: number;
  communities: CommunityInfo[];
}

export interface SimilarEmployee {
  name: string;
  job_type: string | null;
  similarity: number;
  shared_skills: number;
  community_id: number | null;
}

export interface TeamMember {
  name: string;
  job_type: string | null;
  community_id: number | null;
  matched_skills: string[];
  skill_count: number;
}

export interface TeamRecommendResponse {
  success: boolean;
  required_skills: string[];
  members: TeamMember[];
  skill_coverage: number;
  covered_skills: string[];
  missing_skills: string[];
  community_diversity: number;
}

// Additional Analytics Types

export interface DeleteProjectionResponse {
  success: boolean;
  dropped: boolean;
  message: string;
}

export interface CommunityDetectParams {
  algorithm?: 'leiden' | 'louvain';
  gamma?: number;
  min_shared_skills?: number;
}

export interface SimilarEmployeesParams {
  employee_name: string;
  top_k?: number;
}

export interface SimilarEmployeesResponse {
  success: boolean;
  base_employee: string;
  similar_employees: SimilarEmployee[];
}

export interface TeamRecommendParams {
  required_skills: string[];
  team_size?: number;
  diversity_weight?: number;
}

// Project Staffing Types

export interface ProjectListItem {
  name: string;
  status: string | null;
  budget_million: number | null;
  required_headcount: number | null;
}

export interface ProjectListResponse {
  projects: ProjectListItem[];
}

export interface FindCandidatesRequest {
  project_name: string;
  skill_name?: string;
  min_proficiency?: number;
}

export interface CandidateInfo {
  employee_name: string;
  department: string | null;
  proficiency: number;
  effective_rate: number;
  availability: string | null;
  current_projects: number;
  max_projects: number;
}

export interface SkillCandidates {
  skill_name: string;
  required_proficiency: number | null;
  max_hourly_rate: number | null;
  required_headcount: number | null;
  importance: string | null;
  candidates: CandidateInfo[];
}

export interface FindCandidatesResponse {
  project_name: string;
  project_budget: number | null;
  estimated_hours: number | null;
  required_headcount: number | null;
  skill_candidates: SkillCandidates[];
  total_skills: number;
  total_candidates: number;
}

export interface StaffingPlanRequest {
  project_name: string;
  top_n_per_skill?: number;
}

export interface RecommendedCandidate {
  employee_name: string;
  department: string | null;
  proficiency: number;
  effective_rate: number;
  availability: string | null;
}

export interface SkillStaffingPlan {
  skill_name: string;
  importance: string | null;
  required_headcount: number | null;
  recommended_candidates: RecommendedCandidate[];
  estimated_cost_per_hour: number;
}

export interface StaffingPlanResponse {
  project_name: string;
  project_budget: number | null;
  estimated_hours: number | null;
  skill_plans: SkillStaffingPlan[];
  total_estimated_labor_cost: number;
  budget_utilization_percent: number | null;
}

export interface BudgetAnalysisRequest {
  project_name: string;
}

export interface TeamMemberCost {
  employee_name: string;
  role: string | null;
  agreed_rate: number;
  allocated_hours: number;
  actual_hours: number;
  planned_cost: number;
  actual_cost: number;
}

export interface BudgetAnalysisResponse {
  project_name: string;
  project_budget: number | null;
  budget_allocated: number | null;
  budget_spent: number | null;
  team_breakdown: TeamMemberCost[];
  total_planned_cost: number;
  total_actual_cost: number;
  variance: number;
  variance_percent: number | null;
}

export interface SkillCategory {
  name: string;
  color: string;
  skills: string[];
}

export interface SkillCategoryListResponse {
  categories: SkillCategory[];
}
