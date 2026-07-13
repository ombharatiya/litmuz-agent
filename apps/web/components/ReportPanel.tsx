'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { getReport } from '@/lib/api';
import { downloadCsv, reportToCsv } from '@/lib/csv';

import { ClaimCard } from './ClaimCard';
import { ReviewPanel } from './ReviewPanel';

export function ReportPanel({ reportId }: { reportId: string }) {
  const queryClient = useQueryClient();
  const [reviewOpen, setReviewOpen] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: ['report', reportId],
    queryFn: () => getReport(reportId),
    enabled: Boolean(reportId),
  });

  if (isLoading) return <p className="muted">Loading report...</p>;
  if (error)
    return (
      <p className="muted" role="alert">
        Could not load the report.
      </p>
    );

  const report = data!;
  const counts = report.summary_counts ?? {};
  const lights = counts.by_traffic_light ?? {};
  const pending = report.claims.filter((c) => c.routed_to_review && !c.reviewed);

  function onReviewed() {
    void queryClient.invalidateQueries({ queryKey: ['report', reportId] });
    void queryClient.invalidateQueries({ queryKey: ['queue'] });
  }

  return (
    <div>
      <p className="brand">Report</p>
      <h2 className="panel-title">Verification report</h2>

      <div className="summary-bar" data-testid="summary">
        <span className="report-count">
          <strong>{counts.total ?? report.claims.length}</strong> claims
        </span>
        {lights.green ? <span className="report-tally tally-green">{lights.green} grounded</span> : null}
        {lights.yellow ? (
          <span className="report-tally tally-yellow">{lights.yellow} to review</span>
        ) : null}
        {lights.red ? <span className="report-tally tally-red">{lights.red} flagged</span> : null}
        <button
          type="button"
          className="btn-ghost report-review-toggle"
          disabled={pending.length === 0}
          aria-expanded={reviewOpen}
          onClick={() => setReviewOpen((v) => !v)}
        >
          Review queue ({pending.length})
        </button>
        <button
          className="btn-ghost report-export"
          onClick={() => downloadCsv(`litmuz-report-${reportId.slice(0, 8)}.csv`, reportToCsv(report))}
        >
          Export CSV
        </button>
      </div>

      {reviewOpen && (
        <section className="report-review-section">
          <p className="panel-subtitle">This session&#39;s review queue</p>
          <ReviewPanel claims={pending} onReviewed={onReviewed} />
        </section>
      )}

      <div data-testid="claims">
        {report.claims.map((claim) => (
          <ClaimCard key={claim.id} claim={claim} />
        ))}
      </div>
    </div>
  );
}
