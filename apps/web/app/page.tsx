'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';

import { useAuth } from '@/components/AuthProvider';
import { ProgressPanel } from '@/components/ProgressPanel';
import { ReportPanel } from '@/components/ReportPanel';
import { SessionsPanel } from '@/components/SessionsPanel';
import { UpgradeModal } from '@/components/UpgradeModal';
import { ApiError, getJobStatus, getUsage, submitVerification, type Usage } from '@/lib/api';
import type { MyJob } from '@/lib/types';

const MAX_BYTES = 51200;

const EXAMPLE = `TP53 loss drives tumour proliferation [1].
The recommended dose was 5 mg daily [1].
A fabricated result was reported [2].

References
1. Smith J, Doe A. A TP53 study in carcinoma. Nature. 2020. PMID: 12345.
2. Ghost Author. A nonexistent work. 2099. PMID: 99999999.`;

export default function Studio() {
  const { status, canAct, requestSignIn } = useAuth();
  const queryClient = useQueryClient();

  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [overQuota, setOverQuota] = useState<Usage | null>(null);

  // The active verification shown in the right canvas.
  const [jobId, setJobId] = useState<string | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);

  // When a past session is selected from the rail, the composer shows its memo read-only (the
  // input) beside the report (the output), rather than an empty box. Cleared by New verification.
  const [pastSession, setPastSession] = useState<string | null>(null);

  const [sessionsOpen, setSessionsOpen] = useState(true);
  const [canvasOpen, setCanvasOpen] = useState(false);
  const [canvasWidth, setCanvasWidth] = useState(560);
  const dragging = useRef(false);

  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!dragging.current) return;
      const w = window.innerWidth - e.clientX - 24;
      setCanvasWidth(Math.max(380, Math.min(w, window.innerWidth * 0.72)));
    };
    const up = () => {
      dragging.current = false;
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    return () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
  }, []);

  const bytes = new TextEncoder().encode(text).length;
  const tooLarge = bytes > MAX_BYTES;

  const usage = useQuery({
    queryKey: ['usage'],
    queryFn: getUsage,
    enabled: status === 'authenticated',
  });

  const onComplete = useCallback(
    (rid: string) => {
      setReportId(rid);
      queryClient.invalidateQueries({ queryKey: ['my-jobs'] });
      queryClient.invalidateQueries({ queryKey: ['usage'] });
    },
    [queryClient],
  );

  async function doSubmit() {
    setError(null);
    setBusy(true);
    try {
      const { job_id } = await submitVerification(text);
      setPastSession(null);
      setJobId(job_id);
      setReportId(null);
      setCanvasOpen(true);
      queryClient.invalidateQueries({ queryKey: ['my-jobs'] });
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        setOverQuota(e.detail<Usage>());
      } else if (e instanceof ApiError && e.status === 401) {
        requestSignIn(() => void doSubmit());
      } else {
        setError(e instanceof ApiError ? `request failed (${e.status})` : 'request failed');
      }
    } finally {
      setBusy(false);
    }
  }

  function onVerify() {
    if (!canAct) {
      requestSignIn(() => void doSubmit());
      return;
    }
    void doSubmit();
  }

  function onSelectSession(job: MyJob) {
    setError(null);
    setPastSession(job.job_id);
    setJobId(job.job_id);
    setReportId(job.report_id);
    setCanvasOpen(true);
    setText(job.title || job.memo_snippet || '');
    // Load the full memo so the composer shows the exact input behind this report.
    void (async () => {
      try {
        const detail = await getJobStatus(job.job_id);
        if (detail.memo !== undefined) setText(detail.memo);
      } catch {
        // Keep the snippet if the detail read fails; the report is still shown.
      }
    })();
  }

  function onNew() {
    setText('');
    setPastSession(null);
    setJobId(null);
    setReportId(null);
    setError(null);
    setCanvasOpen(false);
  }

  const hasActive = Boolean(jobId || reportId);
  // A verification is in flight while submitting, or once a job exists but its report has not
  // arrived yet. The composer is locked during this window so it cannot be edited or re-submitted.
  const inFlight = busy || (Boolean(jobId) && !reportId && !pastSession);
  const viewing = Boolean(pastSession);
  // The composer is read-only while a run is in flight or when viewing a past session.
  const locked = inFlight || viewing;

  return (
    <div className="studio">
      {sessionsOpen ? (
        <div className="studio-rail">
          <div className="rail-header">
            <span className="rail-title">Sessions</span>
            <button
              type="button"
              className="icon-btn rail-collapse"
              aria-label="Collapse sessions"
              title="Collapse sessions"
              onClick={() => setSessionsOpen(false)}
            >
              <PanelLeftClose />
            </button>
          </div>
          <SessionsPanel activeJobId={jobId} onSelect={onSelectSession} onNew={onNew} />
        </div>
      ) : (
        <button
          type="button"
          className="icon-btn rail-expand"
          aria-label="Show sessions"
          title="Show sessions"
          onClick={() => setSessionsOpen(true)}
        >
          <PanelLeftOpen />
        </button>
      )}

      <section className="studio-main">
        {viewing ? (
          <>
            <p className="brand">Past session</p>
            <h1>Reviewing a verification</h1>
            <p className="muted lede">
              This is the memo you submitted and the report it produced. Start a New verification to
              run a fresh one.
            </p>
          </>
        ) : (
          <>
            <p className="brand">Verify a memo</p>
            <h1>Paste an agent&#39;s memo</h1>
            <p className="muted lede">
              Litmuz decomposes it into atomic claims, checks every citation against the primary
              literature, and returns an auditable, per-claim verdict. It triages and flags; it never
              certifies on its own.
            </p>
          </>
        )}

        <div className="field">
          <div className="field-head">
            <label className="field-label" htmlFor="memo-input">
              {viewing ? 'Submitted memo' : 'Memo'}
            </label>
            {!viewing && (
              <button
                type="button"
                className="auth-link"
                onClick={() => setText(EXAMPLE)}
                disabled={inFlight}
              >
                Load an example
              </button>
            )}
          </div>
          <textarea
            id="memo-input"
            aria-label="memo"
            className={locked ? 'is-locked' : undefined}
            value={text}
            onChange={(e) => setText(e.target.value)}
            readOnly={locked}
            aria-busy={inFlight}
            placeholder="Paste the memo here, including its reference list."
          />
        </div>

        <div className="action-row">
          {viewing ? (
            <button className="button" onClick={onNew}>
              New verification
            </button>
          ) : (
            <>
              <button
                className="button"
                onClick={onVerify}
                disabled={inFlight || !text.trim() || tooLarge}
              >
                {busy ? 'Submitting...' : inFlight ? 'Verifying...' : 'Verify'}
              </button>
              <span className={`byte-count ${tooLarge ? 'byte-over' : ''}`} data-testid="byte-count">
                {bytes.toLocaleString()} / {MAX_BYTES.toLocaleString()} bytes
              </span>
              {usage.data && (
                <span className="usage-pill" title={`${usage.data.tier} plan`}>
                  {usage.data.remaining} of {usage.data.limit} left this week
                </span>
              )}
            </>
          )}
          {!canvasOpen && hasActive && (
            <button className="auth-link" onClick={() => setCanvasOpen(true)}>
              Show result
            </button>
          )}
        </div>

        {inFlight && (
          <p className="composer-lock" role="status">
            Verification in progress. The memo is locked until it finishes; start another with New
            verification.
          </p>
        )}
        {tooLarge && (
          <p className="muted" style={{ color: 'hsl(var(--danger))' }}>
            The memo exceeds the {MAX_BYTES.toLocaleString()} byte limit.
          </p>
        )}
        {error && (
          <p className="muted" role="alert" style={{ color: 'hsl(var(--danger))' }}>
            {error}
          </p>
        )}

        {!viewing && (
          <ol className="steps-hint">
            <li>
              <span className="steps-num">1</span> Every claim is checked against PubMed and PMC.
            </li>
            <li>
              <span className="steps-num">2</span> A red flag means a fabricated or contradicted
              citation; yellow routes to human review.
            </li>
            <li>
              <span className="steps-num">3</span> Safety-critical claims can never auto-pass.
            </li>
          </ol>
        )}
      </section>

      {canvasOpen && (
        <>
          <div
            className="canvas-resizer"
            role="separator"
            aria-orientation="vertical"
            onMouseDown={() => {
              dragging.current = true;
              document.body.style.userSelect = 'none';
            }}
          />
          <section className="studio-canvas" style={{ width: `${canvasWidth}px` }}>
            <header className="canvas-head">
              <span className="canvas-label">Verification</span>
              <button
                className="canvas-close"
                aria-label="Collapse canvas"
                onClick={() => setCanvasOpen(false)}
              >
                &times;
              </button>
            </header>
            <div className="canvas-body">
              {reportId ? (
                <ReportPanel reportId={reportId} />
              ) : jobId ? (
                <ProgressPanel jobId={jobId} onComplete={onComplete} />
              ) : (
                <p className="muted">Submit a memo to see the verification here.</p>
              )}
            </div>
          </section>
        </>
      )}

      {overQuota && <UpgradeModal usage={overQuota} onClose={() => setOverQuota(null)} />}
    </div>
  );
}

// Sidebar collapse/expand glyphs (lucide "panel-left" family): a framed panel with a chevron,
// so the control reads as "hide/show this side panel" rather than a bare arrow.
function PanelLeftClose() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
      <path d="m16 15-3-3 3-3" />
    </svg>
  );
}

function PanelLeftOpen() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="9" y1="3" x2="9" y2="21" />
      <path d="m14 9 3 3-3 3" />
    </svg>
  );
}
