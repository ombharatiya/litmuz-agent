'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { AccountMenu } from './AccountMenu';
import { useAuth } from './AuthProvider';
import { Footer } from './Footer';
import { LoginGate } from './LoginGate';
import { Modal } from './Modal';

const NAV = [
  { href: '/', label: 'Verify' },
  { href: '/queue', label: 'Review queue' },
  { href: '/methodology', label: 'Methodology' },
];

// The app shell. The app is always visible (a soft gate): anyone can browse and start a memo,
// and sign-in is prompted only on an action that needs an account, via the modal. The header
// carries the brand, the primary nav with an active state, and the account menu.
export function AppFrame({ children }: { children: React.ReactNode }) {
  const { status, promptOpen, requestSignIn, closePrompt } = useAuth();
  const pathname = usePathname();

  return (
    <div className="page">
      <div className="brandbar" aria-hidden="true" />
      <div className="shell">
        <header className="nav">
          <Link href="/" className="brand nav-brand">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="" className="nav-mark" />
            Litmuz
          </Link>
          <nav className="nav-links">
            {NAV.map((item) => {
              const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`nav-link ${active ? 'nav-link-active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="nav-right">
            {status === 'authenticated' && <AccountMenu />}
            {status === 'anonymous' && (
              <button className="btn-ghost" onClick={() => requestSignIn()}>
                Sign in
              </button>
            )}
          </div>
        </header>

        <div className="content">{children}</div>

        <Footer />

        {promptOpen && (
          <Modal onClose={closePrompt}>
            <LoginGate heading="Sign in to continue" />
          </Modal>
        )}
      </div>
    </div>
  );
}
