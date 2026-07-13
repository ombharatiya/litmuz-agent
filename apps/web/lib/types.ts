// Wire types mirroring the report JSON emitted by the API.

export type TrafficLight = 'green' | 'yellow' | 'red';
export type JobStatusValue = 'queued' | 'running' | 'completed' | 'failed';

export interface Verdict {
  label: string;
  confidence: number | null;
  rationale: string;
}

// A human reviewer's final verdict label. judge_error is machine-only, so it is not offered.
export type ReviewLabel = 'supported' | 'contradicted' | 'unsupported';

export interface ReviewerAction {
  reviewer_identity: string;
  action: string; // 'accept' | 'override_verdict' | 'add_note'
  prior_verdict: Verdict | null;
  new_verdict: Verdict | null;
  note: string;
  created_at: string;
}

export interface CitationCheck {
  identifier: string;
  id_type: string;
  resolution_status: string;
  source_status: string | null;
  title_match: string;
  author_match: string;
  year_match: string;
  resolver_path: string;
}

export interface Evidence {
  evidence_sentence: string | null;
  source_locator: Record<string, unknown> | null;
  evidence_not_located: boolean;
}

export interface Claim {
  id: string;
  ordinal: number;
  text: string;
  cited_ids: { id_type: string; value: string }[];
  citation_checks: CitationCheck[];
  retrieval_mode: string | null;
  evidence: Evidence | null;
  verdict: Verdict | null;
  category: string | null;
  diagnostic: string | null;
  traffic_light: TrafficLight | null;
  auto_pass_blocked: boolean | null;
  auto_passed: boolean | null;
  routed_to_review: boolean | null;
  reviewer_actions: ReviewerAction[];
  effective_verdict: Verdict | null;
  // Projected from reviewer_actions: the light after a human's terminal decision (the pipeline
  // traffic_light above is never mutated). reviewed is true once an accept or override_verdict
  // has landed; a bare note never sets it.
  effective_traffic_light: TrafficLight | null;
  reviewed: boolean;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_action: string | null;
}

export interface Report {
  id: string;
  job_id: string;
  memo_hash: string;
  summary_counts: {
    total?: number;
    by_traffic_light?: Record<string, number>;
    by_category?: Record<string, number>;
    routed_to_review?: number;
  };
  unclaimed_spans: { start: number; end: number }[];
  claims: Claim[];
  created_at: string;
}

export interface JobStatus {
  job_id: string;
  status: JobStatusValue;
  stage: string | null;
  claims_done: number;
  claims_total: number;
  report_id: string | null;
  // Present on the job-detail read so a past session can show its input beside the report.
  memo?: string;
  title?: string;
}

export interface MyJob {
  job_id: string;
  status: JobStatusValue;
  stage: string | null;
  report_id: string | null;
  created_at: string;
  title: string;
  memo_snippet: string;
}

export interface QueueItem {
  claim_id: string;
  report_id: string;
  text: string;
  category: string;
  diagnostic: string;
  traffic_light: string;
}
