import type { JobStatus, MyJob, QueueItem, Report, ReviewLabel, VerificationMode } from './types';

import { authHeaders } from './auth';

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

export interface Usage {
  tier: string;
  used: number;
  limit: number;
  remaining: number;
  resets_at: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: string,
  ) {
    super(`API ${status}: ${body}`);
    this.name = 'ApiError';
  }

  // The structured detail from a JSON error body ({"detail": ...}), or null.
  detail<T = unknown>(): T | null {
    try {
      return JSON.parse(this.body).detail as T;
    } catch {
      return null;
    }
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(await authHeaders()),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text().catch(() => ''));
  }
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const submitVerification = (text: string, mode: VerificationMode = 'literature') =>
  request<{ job_id: string }>('/verifications', {
    method: 'POST',
    body: JSON.stringify({ text, mode }),
  });

export const getJobStatus = (jobId: string) => request<JobStatus>(`/verifications/${jobId}`);

export const getReport = (reportId: string) => request<Report>(`/reports/${reportId}`);

export const getQueue = () => request<QueueItem[]>('/queue');

export const getUsage = () => request<Usage>('/me/usage');

export const getMyJobs = () => request<MyJob[]>('/me/jobs');

export const postReview = (
  claimId: string,
  body: { action: string; note?: string; new_verdict?: unknown },
) => request<void>(`/queue/${claimId}/review`, { method: 'POST', body: JSON.stringify(body) });

// Confirms the claim's current (machine) verdict as the final call; resolves it and removes
// it from the review queue without changing anything.
export const acceptClaim = (claimId: string, note?: string) =>
  postReview(claimId, { action: 'accept', note });

// Records the reviewer's final verdict for the claim. This is the terminal, human-authoritative
// call: it replaces the effective verdict and re-derives the claim's effective traffic light,
// and resolves the claim out of the queue. A rationale is required by the API.
export const overrideClaim = (
  claimId: string,
  body: { label: ReviewLabel; confidence?: number; rationale: string },
) => postReview(claimId, { action: 'override_verdict', new_verdict: body });

// Appends a note without resolving the claim; it stays in the queue.
export const addClaimNote = (claimId: string, note: string) =>
  postReview(claimId, { action: 'add_note', note });

export const reportExportUrl = (reportId: string) => `${API_BASE}/reports/${reportId}/export`;
