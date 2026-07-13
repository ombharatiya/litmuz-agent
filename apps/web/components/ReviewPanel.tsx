'use client';

import type { Claim } from '@/lib/types';

import { ReviewForm } from './ReviewForm';

// The session-scoped review queue: every claim from this report still awaiting a human decision.
// Lazily mounted by ReportPanel only once the reviewer opens it, so a report with nothing flagged
// never pays for this panel at all.
export function ReviewPanel({
  claims,
  onReviewed,
}: {
  claims: Claim[];
  onReviewed: () => void;
}) {
  if (claims.length === 0) {
    return <p className="muted review-panel-empty">Nothing left to review in this session.</p>;
  }
  return (
    <div className="review-panel" data-testid="session-review">
      {claims.map((claim) => (
        <div key={claim.id} className="review-panel-item">
          <ReviewForm
            claimId={claim.id}
            text={claim.text}
            category={claim.category}
            diagnostic={claim.diagnostic}
            trafficLight={claim.traffic_light}
            onReviewed={onReviewed}
          />
        </div>
      ))}
    </div>
  );
}
