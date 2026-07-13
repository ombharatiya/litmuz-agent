import Link from 'next/link';

export function Footer() {
  const year = 2026;
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <span className="brand">Litmuz</span>
          <p className="muted footer-tag">
            Claim-level verification for life-sciences research. It triages and flags; it never
            certifies on its own.
          </p>
        </div>
        <nav className="footer-links">
          <Link href="/">Verify</Link>
          <Link href="/methodology">Methodology</Link>
          <Link href="/queue">Review queue</Link>
          <Link href="/contact">Contact</Link>
        </nav>
      </div>
      <div className="footer-legal muted">© {year} Litmuz</div>
    </footer>
  );
}
