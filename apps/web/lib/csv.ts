import type { Report } from './types';
import { verdictStyle } from './verdict';

// Build a CSV from the report JSON we already hold. This is why the export works without a
// second, unauthenticated request to the protected /export URL (which 401s): the report is
// already fetched with the bearer token, so we just serialize it in the browser.

function cell(value: unknown): string {
  const s = value == null ? '' : String(value);
  // Quote every field and double any embedded quotes; RFC-4180 safe.
  return `"${s.replace(/"/g, '""')}"`;
}

const HEADERS = [
  'claim_number',
  'verdict',
  'traffic_light',
  'diagnostic',
  'category',
  'routed_to_review',
  'reviewed',
  'reviewed_by',
  'reviewed_at',
  'review_action',
  'pipeline_verdict',
  'pipeline_traffic_light',
  'claim_text',
  'citations',
  'citation_status',
  'evidence_sentence',
  'confidence',
];

export function reportToCsv(report: Report): string {
  const rows = report.claims.map((claim) => {
    // The verdict/traffic_light columns are the FINAL, human-calibrated assessment when a
    // claim has been reviewed (matching what the report itself shows); the pipeline_* columns
    // preserve the original machine result for audit, unmutated either way.
    const effectiveLight = claim.effective_traffic_light ?? claim.traffic_light;
    const style = verdictStyle(effectiveLight);
    const citations = claim.cited_ids.map((c) => `${c.id_type}:${c.value}`).join('; ');
    const citationStatus = claim.citation_checks.map((c) => c.resolution_status).join('; ');
    const evidence = claim.evidence?.evidence_sentence ?? '';
    const confidence = claim.effective_verdict?.confidence ?? claim.verdict?.confidence ?? '';
    return [
      claim.ordinal + 1,
      style.label,
      effectiveLight ?? '',
      claim.diagnostic ?? '',
      claim.category ?? '',
      claim.routed_to_review ? 'yes' : 'no',
      claim.reviewed ? 'yes' : 'no',
      claim.reviewed_by ?? '',
      claim.reviewed_at ?? '',
      claim.review_action ?? '',
      claim.verdict?.label ?? '',
      claim.traffic_light ?? '',
      claim.text,
      citations,
      citationStatus,
      evidence,
      confidence,
    ]
      .map(cell)
      .join(',');
  });
  return [HEADERS.map(cell).join(','), ...rows].join('\r\n');
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
