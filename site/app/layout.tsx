import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Grahama Labs — Applied Research Engineering for Agentic Systems',
  description:
    'Multi-agent orchestration, self-improving skill ecosystems, and verified autonomy — taken from paper to production discipline. No claim ships without a receipt.',
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
