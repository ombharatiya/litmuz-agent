'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';

import { ReviewForm } from '@/components/ReviewForm';
import { getQueue } from '@/lib/api';
import type { TrafficLight } from '@/lib/types';

export default function QueuePage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ['queue'], queryFn: getQueue });

  if (isLoading) return <p className="muted">Loading queue...</p>;
  if (error)
    return (
      <p className="muted" role="alert">
        Could not load the queue.
      </p>
    );

  const items = data ?? [];
  return (
    <main className="narrow">
      <p className="brand">Human review</p>
      <h1>Review queue</h1>
      <p className="muted lede">
        Every flagged or safety-critical claim across your verifications, across all sessions.
        Reviewing a claim here resolves it and removes it from this list.
      </p>
      {items.length === 0 && <p className="muted">Nothing is flagged for review.</p>}
      <div data-testid="queue">
        {items.map((item) => (
          <article
            key={item.claim_id}
            className="claim-card"
            data-claim-id={item.claim_id}
            data-light={item.traffic_light}
          >
            <ReviewForm
              claimId={item.claim_id}
              text={item.text}
              category={item.category}
              diagnostic={item.diagnostic}
              trafficLight={item.traffic_light as TrafficLight}
              onReviewed={() => qc.invalidateQueries({ queryKey: ['queue'] })}
            />
          </article>
        ))}
      </div>
    </main>
  );
}
