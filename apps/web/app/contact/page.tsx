import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Contact - Litmuz',
  description: 'Get in touch with the Litmuz team.',
};

export default function ContactPage() {
  return (
    <main className="narrow prose">
      <p className="brand">Contact</p>
      <h1>Get in touch</h1>
      <p className="muted lede">
        Questions about a verdict, an enterprise plan, or a qualified review of the methodology - we
        are happy to talk.
      </p>

      <div className="contact-grid">
        <div className="contact-card">
          <h2>General</h2>
          <p>
            Email <a href="mailto:coffeewithom@gmail.com">coffeewithom@gmail.com</a> and we will get
            back to you.
          </p>
        </div>
        <div className="contact-card">
          <h2>Upgrade to Pro</h2>
          <p>
            Want a higher weekly quota? Email{' '}
            <a href="mailto:coffeewithom@gmail.com?subject=Upgrade%20to%20Litmuz%20Pro">
              coffeewithom@gmail.com
            </a>{' '}
            and we will set you up.
          </p>
        </div>
        <div className="contact-card">
          <h2>Methodology review</h2>
          <p>
            For a deeper technical assurance under agreement, ask for a methodology walkthrough at{' '}
            <a href="mailto:coffeewithom@gmail.com?subject=Methodology%20review">
              coffeewithom@gmail.com
            </a>
            .
          </p>
        </div>
      </div>

      <div className="contact-person">
        <h2>Behind Litmuz</h2>
        <p className="contact-name">Om Bharatiya</p>
        <nav className="contact-socials">
          <a href="https://www.ombharatiya.com" target="_blank" rel="noopener noreferrer">
            ombharatiya.com
          </a>
          <a
            href="https://www.linkedin.com/in/ombharatiya"
            target="_blank"
            rel="noopener noreferrer"
          >
            LinkedIn
          </a>
          <a href="https://twitter.com/ombharatiya" target="_blank" rel="noopener noreferrer">
            Twitter / X
          </a>
        </nav>
      </div>
    </main>
  );
}
