'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

import { ProgressPanel } from '@/components/ProgressPanel';

function ProgressView() {
  const jobId = useSearchParams().get('job') ?? '';
  const router = useRouter();
  if (!jobId) return <p className="muted">No job id.</p>;
  return (
    <main className="narrow">
      <ProgressPanel
        jobId={jobId}
        onComplete={(reportId) => router.push(`/report?id=${encodeURIComponent(reportId)}`)}
      />
    </main>
  );
}

export default function ProgressPage() {
  return (
    <Suspense fallback={<p className="muted">Preparing...</p>}>
      <ProgressView />
    </Suspense>
  );
}
