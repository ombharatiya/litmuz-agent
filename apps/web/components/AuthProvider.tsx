'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { AUTH_ENABLED, hasStoredSession } from '@/lib/auth';
import type { Session } from '@/lib/cognito';

type Status = 'disabled' | 'restoring' | 'anonymous' | 'authenticated';

interface AuthState {
  status: Status;
  session: Session | null;
  // True when auth is off (open mode) or the user is signed in: they may act freely.
  canAct: boolean;
  promptOpen: boolean;
  // Open the sign-in modal. The optional callback runs once, right after a successful sign-in
  // (used to resume the action the user was attempting, e.g. submitting a memo).
  requestSignIn: (onDone?: () => void) => void;
  closePrompt: () => void;
  adopt: (session: Session) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>(AUTH_ENABLED ? 'restoring' : 'disabled');
  const [session, setSession] = useState<Session | null>(null);
  const [promptOpen, setPromptOpen] = useState(false);
  const pending = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!AUTH_ENABLED) return;
    if (!hasStoredSession()) {
      setStatus('anonymous');
      return;
    }
    let cancelled = false;
    (async () => {
      const { getIdToken, currentSession } = await import('@/lib/cognito');
      const token = await getIdToken();
      if (cancelled) return;
      const s = token ? currentSession() : null;
      setSession(s);
      setStatus(s ? 'authenticated' : 'anonymous');
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const requestSignIn = useCallback((onDone?: () => void) => {
    pending.current = onDone ?? null;
    setPromptOpen(true);
  }, []);

  const closePrompt = useCallback(() => {
    pending.current = null;
    setPromptOpen(false);
  }, []);

  const adopt = useCallback((s: Session) => {
    setSession(s);
    setStatus('authenticated');
    setPromptOpen(false);
    const run = pending.current;
    pending.current = null;
    if (run) run();
  }, []);

  const signOut = useCallback(async () => {
    const { signOut: revoke } = await import('@/lib/cognito');
    await revoke();
    setSession(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      status,
      session,
      canAct: status === 'disabled' || status === 'authenticated',
      promptOpen,
      requestSignIn,
      closePrompt,
      adopt,
      signOut,
    }),
    [status, session, promptOpen, requestSignIn, closePrompt, adopt, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
