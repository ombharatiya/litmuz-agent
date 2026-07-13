import type { Metadata, Viewport } from 'next';

import { AppFrame } from '@/components/AppFrame';

import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: 'Litmuz',
  description:
    'Claim-level verification for life-sciences research agents. Litmuz triages and flags; it never certifies on its own.',
  manifest: '/site.webmanifest',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/logo.svg', type: 'image/svg+xml' },
      { url: '/favicon-32x32.png', type: 'image/png', sizes: '32x32' },
      { url: '/favicon-16x16.png', type: 'image/png', sizes: '16x16' },
    ],
    apple: '/apple-touch-icon.png',
  },
};

export const viewport: Viewport = {
  themeColor: '#00674F',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <AppFrame>{children}</AppFrame>
        </Providers>
      </body>
    </html>
  );
}
