'use client';

import type { Usage } from '@/lib/api';

import { Modal } from './Modal';

const SUPPORT_EMAIL = 'coffeewithom@gmail.com';

// Shown when a free user hits their weekly quota. Presents Pro and a way to upgrade. Real
// checkout (Stripe) is a follow-up; for now the CTA opens a pre-filled upgrade request.
export function UpgradeModal({ usage, onClose }: { usage: Usage; onClose: () => void }) {
  const resets = new Date(usage.resets_at).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  });
  const mailto = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(
    'Upgrade to Litmuz Pro',
  )}&body=${encodeURIComponent('I would like to upgrade to the Pro plan (100 verifications a week).')}`;

  return (
    <Modal onClose={onClose}>
      <p className="brand">Upgrade</p>
      <h1>You have used your free verifications</h1>
      <p className="muted auth-lede">
        The free plan includes {usage.limit} verifications a week. Your allowance resets {resets}.
      </p>

      <div className="plan">
        <div className="plan-head">
          <span className="plan-name">Pro</span>
          <span className="plan-price">100 verifications / week</span>
        </div>
        <ul className="plan-list">
          <li>50x the weekly quota</li>
          <li>The same claim-level checks and honest, per-claim verdicts</li>
          <li>Priority support</li>
        </ul>
      </div>

      <a className="button auth-submit" href={mailto}>
        Upgrade to Pro
      </a>
      <button type="button" className="auth-link plan-later" onClick={onClose}>
        Maybe later
      </button>
    </Modal>
  );
}
