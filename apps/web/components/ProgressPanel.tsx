'use client';

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

import { getJobStatus } from '@/lib/api';
import type { JobStatus } from '@/lib/types';

type PhaseState = 'done' | 'active' | 'pending';

// The three phases the pipeline reports (decompose, per-claim verify, report). Each carries a
// plain-language account of the work, describing what it does without exposing prompts, model
// names, or internal tooling.
const PHASES = [
  {
    key: 'decompose',
    title: 'Break the memo into claims',
    detail:
      'Reading the memo and splitting it into atomic, independently checkable claims, with their citations.',
  },
  {
    key: 'verify',
    title: 'Check every claim against the literature',
    detail: 'For each claim, in order:',
    substeps: [
      'Resolve its citations against the primary literature and flag anything fabricated, retracted, or mismatched.',
      'Retrieve the cited and related source text.',
      'Judge whether that evidence actually supports the claim, quoting the sentence it relied on.',
      'Classify each claim and hold safety-critical or unresolved ones for human review.',
    ],
  },
  {
    key: 'report',
    title: 'Compile the verdict',
    detail: 'Assembling the auditable, per-claim report with a traffic-light verdict for each.',
  },
] as const;

function phaseState(key: string, data: JobStatus): PhaseState {
  const { status, stage } = data;
  if (status === 'completed') return 'done';
  if (key === 'decompose') {
    if (stage === 'verify') return 'done';
    if (stage === 'decompose' || status === 'running') return 'active';
    return 'pending';
  }
  if (key === 'verify') return stage === 'verify' ? 'active' : 'pending';
  return 'pending'; // report
}

export function ProgressPanel({
  jobId,
  onComplete,
}: {
  jobId: string;
  onComplete?: (reportId: string) => void;
}) {
  const { data, error } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJobStatus(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'completed' || status === 'failed' ? false : 1000;
    },
  });

  useEffect(() => {
    if (data?.status === 'completed' && data.report_id) onComplete?.(data.report_id);
  }, [data, onComplete]);

  if (error)
    return (
      <p className="muted" role="alert">
        Could not load job status.
      </p>
    );
  if (!data) return <p className="muted">Preparing...</p>;

  const failed = data.status === 'failed';

  return (
    <div>
      <p className="brand">Verifying</p>
      <h2 className="panel-title">Working through the memo</h2>
      <p className="muted" data-testid="job-status">
        This runs live against the primary literature, so it takes a moment.
      </p>

      <ol className="steps">
        {PHASES.map((phase) => {
          const state = failed ? 'pending' : phaseState(phase.key, data);
          const showCount = phase.key === 'verify' && state === 'active' && data.claims_total > 0;
          return (
            <li key={phase.key} className={`step step-${state}`}>
              <span className="step-dot" aria-hidden="true">
                {state === 'done' ? '✓' : ''}
              </span>
              <div className="step-body">
                <div className="step-title">
                  {phase.title}
                  {showCount && (
                    <span className="step-count">
                      claim {data.claims_done} of {data.claims_total}
                    </span>
                  )}
                </div>
                <p className="step-detail">{phase.detail}</p>
                {'substeps' in phase && state === 'active' && (
                  <ul className="step-subs">
                    {phase.substeps.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {failed && (
        <p className="auth-alert" role="alert">
          Something went wrong verifying this memo. Please try again.
        </p>
      )}
    </div>
  );
}
