'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

import { ReportPanel } from '@/components/ReportPanel';

function ReportView() {
  const reportId = useSearchParams().get('id') ?? '';
  if (!reportId) return <p className="muted">No report id.</p>;
  return (
    <main className="narrow">
      <ReportPanel reportId={reportId} />
    </main>
  );
}

export default function ReportPage() {
  return (
    <Suspense fallback={<p className="muted">Loading...</p>}>
      <ReportView />
    </Suspense>
  );
}
