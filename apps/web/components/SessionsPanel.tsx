'use client';

import { useQuery } from '@tanstack/react-query';

import { getMyJobs } from '@/lib/api';
import type { MyJob } from '@/lib/types';

import { useAuth } from './AuthProvider';

const STATUS_DOT: Record<string, string> = {
  completed: 'dot-done',
  running: 'dot-run',
  queued: 'dot-run',
  failed: 'dot-fail',
};

export function SessionsPanel({
  activeJobId,
  onSelect,
  onNew,
}: {
  activeJobId: string | null;
  onSelect: (job: MyJob) => void;
  onNew: () => void;
}) {
  const { canAct } = useAuth();
  const { data } = useQuery({
    queryKey: ['my-jobs'],
    queryFn: getMyJobs,
    enabled: canAct,
    // Keep the list fresh while a verification is in flight.
    refetchInterval: 5000,
  });
  const jobs = data ?? [];

  return (
    <aside className="sessions">
      <button className="btn-ghost sessions-new" onClick={onNew}>
        + New verification
      </button>
      <p className="sessions-label">History</p>
      {jobs.length === 0 ? (
        <p className="muted sessions-empty">Your past verifications appear here.</p>
      ) : (
        <ul className="sessions-list">
          {jobs.map((job) => (
            <li key={job.job_id}>
              <button
                className={`session-item ${job.job_id === activeJobId ? 'session-active' : ''}`}
                onClick={() => onSelect(job)}
              >
                <span className={`session-dot ${STATUS_DOT[job.status] ?? 'dot-run'}`} aria-hidden="true" />
                <span className="session-text">
                  {job.title || job.memo_snippet || 'Untitled memo'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
