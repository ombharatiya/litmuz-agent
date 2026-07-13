import type { Claim, Verdict } from '@/lib/types';
import { verdictStyle } from '@/lib/verdict';

import { VerdictBadge } from './VerdictBadge';

const CATEGORY_LABEL: Record<string, string> = {
  citation: 'Citation',
  mechanistic: 'Mechanistic',
  safety_critical: 'Safety-critical',
};

function whyLine(claim: Claim, verdict: Verdict | null, reviewed: boolean): string {
  const label = verdict ? verdict.label.replace('_', ' ') : 'not judged';
  const diagnostic = claim.diagnostic ?? 'n/a';
  const citation = claim.citation_checks[0]?.resolution_status ?? 'uncited';
  let line = `Verdict: ${label} (${diagnostic}). Citation: ${citation}.`;
  if (claim.routed_to_review && !reviewed) line += ' Routed to human review.';
  return line;
}

function formatWhen(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export function ClaimCard({ claim }: { claim: Claim }) {
  const reviewed = Boolean(claim.reviewed);
  const effectiveLight = claim.effective_traffic_light ?? claim.traffic_light;
  const style = verdictStyle(effectiveLight);
  const verdict = claim.effective_verdict ?? claim.verdict;
  const overridden = reviewed && claim.review_action === 'override_verdict';

  return (
    <article
      className={`claim-card claim-${style.token}`}
      data-light={effectiveLight ?? 'pending'}
      data-token={style.token}
      data-claim-id={claim.id}
      data-reviewed={reviewed ? 'true' : 'false'}
    >
      <div className="claim-head">
        <VerdictBadge light={effectiveLight} />
        {claim.category && (
          <span className="claim-category" data-category={claim.category}>
            {CATEGORY_LABEL[claim.category] ?? claim.category}
          </span>
        )}
        {claim.routed_to_review && !reviewed && (
          <span className="claim-routed" data-routed="true">
            Routed to review
          </span>
        )}
        {reviewed && (
          <span className="claim-reviewed" data-review-action={claim.review_action ?? ''}>
            {overridden ? 'Reviewed - verdict changed' : 'Reviewed - confirmed'}
          </span>
        )}
      </div>
      <p className="claim-text">{claim.text}</p>
      <p className="claim-why">{whyLine(claim, verdict, reviewed)}</p>
      {claim.evidence?.evidence_sentence && (
        <blockquote className="claim-evidence">{claim.evidence.evidence_sentence}</blockquote>
      )}

      {reviewed && (
        <div className="claim-audit" data-testid="claim-audit">
          <p className="claim-audit-head">
            {overridden
              ? `Reviewed by human: ${verdict?.label.replace('_', ' ') ?? ''}.`
              : 'Confirmed as shown by human review.'}
          </p>
          <p className="muted claim-audit-meta">
            {claim.reviewed_by}
            {claim.reviewed_at ? ` - ${formatWhen(claim.reviewed_at)}` : ''}
          </p>
          {overridden && verdict?.rationale && (
            <p className="muted claim-audit-rationale">&ldquo;{verdict.rationale}&rdquo;</p>
          )}
          {overridden && (
            <p className="muted claim-audit-original">
              Original machine verdict:{' '}
              {claim.verdict ? claim.verdict.label.replace('_', ' ') : 'not judged'} (
              {claim.diagnostic ?? 'n/a'}).
            </p>
          )}
        </div>
      )}
    </article>
  );
}
