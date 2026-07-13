'use client';

import { useState } from 'react';

import { acceptClaim, addClaimNote, overrideClaim } from '@/lib/api';
import type { ReviewLabel, TrafficLight } from '@/lib/types';

import { VerdictBadge } from './VerdictBadge';

type Decision = 'accept' | ReviewLabel;

const DECISIONS: { key: Decision; label: string }[] = [
  { key: 'accept', label: 'Confirm as shown' },
  { key: 'supported', label: 'Mark grounded' },
  { key: 'contradicted', label: 'Mark flagged' },
  { key: 'unsupported', label: 'Mark still unsupported' },
];

// The reviewer decision form for one flagged claim, shared by the global review queue and the
// per-session review panel. A decision is either a bare accept (the machine verdict stands, but
// the claim is now resolved) or an override that becomes the claim's final, human-authoritative
// verdict; overrides require a rationale so the decision is auditable, not just a click.
export function ReviewForm({
  claimId,
  text,
  category,
  diagnostic,
  trafficLight,
  onReviewed,
}: {
  claimId: string;
  text: string;
  category?: string | null;
  diagnostic?: string | null;
  trafficLight?: TrafficLight | null;
  onReviewed: () => void;
}) {
  const [decision, setDecision] = useState<Decision | null>(null);
  const [rationale, setRationale] = useState('');
  const [confidence, setConfidence] = useState('');
  const [note, setNote] = useState('');
  const [noteOpen, setNoteOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsRationale = decision !== null && decision !== 'accept';

  async function submitDecision() {
    if (!decision) return;
    setError(null);
    setBusy(true);
    try {
      if (decision === 'accept') {
        await acceptClaim(claimId);
      } else {
        const conf = confidence.trim() ? Number(confidence) : undefined;
        await overrideClaim(claimId, { label: decision, confidence: conf, rationale });
      }
      onReviewed();
    } catch {
      setError('Could not save the review. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  async function submitNote() {
    if (!note.trim()) return;
    setError(null);
    setBusy(true);
    try {
      await addClaimNote(claimId, note);
      setNote('');
      setNoteOpen(false);
    } catch {
      setError('Could not save the note. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="review-form" data-claim-id={claimId}>
      <div className="review-form-head">
        <VerdictBadge light={trafficLight ?? null} />
        {category && <span className="claim-category">{category}</span>}
        {diagnostic && <span className="muted review-diagnostic">{diagnostic}</span>}
      </div>
      <p className="claim-text">{text}</p>

      <div className="review-decisions" role="group" aria-label="Review decision">
        {DECISIONS.map((d) => (
          <button
            key={d.key}
            type="button"
            className={`review-decision ${decision === d.key ? 'review-decision-active' : ''}`}
            onClick={() => setDecision(d.key)}
            disabled={busy}
          >
            {d.label}
          </button>
        ))}
      </div>

      {needsRationale && (
        <div className="review-fields">
          <label className="field-label" htmlFor={`rationale-${claimId}`}>
            Rationale (required)
          </label>
          <textarea
            id={`rationale-${claimId}`}
            className="review-rationale"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="Why is this the final call? What did you check?"
          />
          <label className="field-label" htmlFor={`confidence-${claimId}`}>
            Confidence (optional, 0-1)
          </label>
          <input
            id={`confidence-${claimId}`}
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={confidence}
            onChange={(e) => setConfidence(e.target.value)}
            className="review-confidence"
          />
        </div>
      )}

      {decision && (
        <button
          type="button"
          className="button review-submit"
          onClick={() => void submitDecision()}
          disabled={busy || (needsRationale && !rationale.trim())}
        >
          {busy ? 'Saving...' : decision === 'accept' ? 'Confirm' : 'Submit review'}
        </button>
      )}

      {error && (
        <p className="muted" role="alert" style={{ color: 'hsl(var(--danger))' }}>
          {error}
        </p>
      )}

      {noteOpen ? (
        <div className="review-note-open">
          <textarea
            className="review-note-text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add a note without resolving this claim..."
          />
          <div className="review-note-actions">
            <button
              type="button"
              className="auth-link"
              onClick={() => void submitNote()}
              disabled={busy || !note.trim()}
            >
              Save note
            </button>
            <button
              type="button"
              className="auth-link"
              onClick={() => setNoteOpen(false)}
              disabled={busy}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="auth-link review-note-toggle"
          onClick={() => setNoteOpen(true)}
        >
          + Add a note without resolving
        </button>
      )}
    </div>
  );
}
