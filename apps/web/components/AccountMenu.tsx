'use client';

import { useEffect, useRef, useState } from 'react';

import { useAuth } from './AuthProvider';

// The signed-in identity, collapsed into an avatar button that opens a small menu. Sign out
// lives inside it rather than bare in the nav. Closes on outside-click or Escape.
export function AccountMenu() {
  const { session, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!session) return null;
  const initial = (session.email.trim()[0] || '?').toUpperCase();

  return (
    <div className="account" ref={ref}>
      <button
        className="account-avatar"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        onClick={() => setOpen((v) => !v)}
      >
        {initial}
      </button>
      {open && (
        <div className="account-pop" role="menu">
          <div className="account-head">
            <span className="account-label">Signed in as</span>
            <span className="account-email">{session.email}</span>
          </div>
          <button
            className="account-item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              void signOut();
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
