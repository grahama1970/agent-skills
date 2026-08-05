import type { Metadata } from 'next';
import './globals.css';

const description =
  'Multi-agent orchestration, self-improving skill ecosystems, and verified autonomy — taken from paper to production discipline. No claim ships without a receipt.';

export const metadata: Metadata = {
  metadataBase: new URL('https://grahama.co'),
  title: 'Grahama Labs — Applied Research Engineering for Agentic Systems',
  description,
  openGraph: {
    title: 'Grahama Labs',
    description,
    url: 'https://grahama.co',
    siteName: 'Grahama Labs',
    type: 'website',
  },
  twitter: {
    card: 'summary',
    title: 'Grahama Labs',
    description,
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
