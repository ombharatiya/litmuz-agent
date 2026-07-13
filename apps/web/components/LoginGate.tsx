'use client';

import { useEffect, useRef, useState } from 'react';

import { useAuth } from './AuthProvider';

type Flow = 'signin' | 'signup';
type Step = { flow: Flow; session: string; email: string } | null;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// The email -> one-time-code card. Used inside the sign-in modal. On success it calls adopt(),
// which closes the modal and resumes whatever the user was doing.
export function LoginGate({ heading = 'Sign in' }: { heading?: string }) {
  const { adopt } = useAuth();
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<Step>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  useEffect(() => {
    if (step) codeRef.current?.focus();
  }, [step]);

  async function sendCode(e?: React.FormEvent) {
    e?.preventDefault();
    if (!EMAIL_RE.test(email.trim())) {
      setError('Please enter a valid email address.');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const { beginEmailAuth } = await import('@/lib/cognito');
      const result = await beginEmailAuth(email);
      setStep(result);
      setCooldown(30);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send a code.');
    } finally {
      setBusy(false);
    }
  }

  async function verify(e?: React.FormEvent) {
    e?.preventDefault();
    if (!step) return;
    setError(null);
    setBusy(true);
    try {
      const cognito = await import('@/lib/cognito');
      const session =
        step.flow === 'signup'
          ? await cognito.submitSignUpOtp(step.email, code.trim())
          : await cognito.submitSignInOtp(step.email, code.trim(), step.session);
      adopt(session);
    } catch (err) {
      const code2 =
        err && typeof err === 'object' && 'code' in err ? String((err as { code: unknown }).code) : '';
      if (code2 === 'AutoSignInFailed' && step.flow === 'signup') {
        setStep({ ...step, flow: 'signin' });
      }
      setError(err instanceof Error ? err.message : 'That code did not work.');
      setBusy(false);
    }
  }

  async function resend() {
    if (!step || cooldown > 0) return;
    setError(null);
    try {
      const { resendCode } = await import('@/lib/cognito');
      const session = await resendCode(step.email, step.flow);
      setStep({ ...step, session: session || step.session });
      setCooldown(30);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not resend the code.');
    }
  }

  function reset() {
    setStep(null);
    setCode('');
    setError(null);
  }

  const codeLength = step?.flow === 'signup' ? 6 : 8;

  return !step ? (
    <form onSubmit={sendCode}>
      <p className="brand">Litmuz</p>
      <h1>{heading}</h1>
      <p className="muted auth-lede">
        Enter your email and we will send a one-time code. No password to remember.
      </p>
      <label className="auth-label" htmlFor="auth-email">
        Email
      </label>
      <input
        id="auth-email"
        className="auth-input"
        type="email"
        autoComplete="email"
        autoFocus
        spellCheck={false}
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@lab.org"
      />
      <button className="button auth-submit" type="submit" disabled={busy || !email.trim()}>
        {busy ? 'Sending code...' : 'Continue with email'}
      </button>
      {error && (
        <p className="auth-alert" role="alert">
          {error}
        </p>
      )}
    </form>
  ) : (
    <form onSubmit={verify}>
      <p className="brand">Litmuz</p>
      <h1>Check your email</h1>
      <p className="muted auth-lede">
        We emailed a {codeLength}-digit code to <strong>{step.email}</strong>. Enter it to continue.
      </p>
      <label className="auth-label" htmlFor="auth-code">
        Verification code
      </label>
      <input
        id="auth-code"
        ref={codeRef}
        className="auth-input auth-code"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={codeLength}
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
        placeholder={'0'.repeat(codeLength)}
      />
      <button
        className="button auth-submit"
        type="submit"
        disabled={busy || code.trim().length < codeLength}
      >
        {busy ? 'Verifying...' : 'Verify and continue'}
      </button>
      {error && (
        <p className="auth-alert" role="alert">
          {error}
        </p>
      )}
      <div className="auth-foot">
        <button type="button" className="auth-link" onClick={resend} disabled={cooldown > 0}>
          {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend code'}
        </button>
        <button type="button" className="auth-link" onClick={reset}>
          Use a different email
        </button>
      </div>
    </form>
  );
}
