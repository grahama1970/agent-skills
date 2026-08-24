import type { Metadata, Viewport } from 'next';
import { ProjectTargetHighlighter } from '@/components/project-target-highlighter';
import './globals.css';

const description =
  'I build agent systems that leave evidence of what they did. One-person applied research practice: multi-agent harnesses, evaluation, evidence extraction, and working public code.';

export const metadata: Metadata = {
  metadataBase: new URL('https://grahama.co'),
  title: 'Graham Anderson — agent systems with evidence',
  description,
  manifest: '/site.webmanifest',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: '32x32' },
      { url: '/icon.svg', type: 'image/svg+xml' },
    ],
    apple: [{ url: '/apple-touch-icon.png' }],
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Graham Resume',
  },
  openGraph: {
    title: 'Graham Anderson — agent systems with evidence',
    description,
    url: 'https://grahama.co',
    siteName: 'grahama.co',
    type: 'website',
    images: [{ url: '/og.png', width: 1200, height: 630, alt: 'grahama.co — G꜀ mark, agent systems with evidence' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Graham Anderson — agent systems with evidence',
    description,
    images: ['/og.png'],
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#0a0a0a' },
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link
          rel="preload"
          href="/fonts/fraunces-site-subset.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
        <meta name="apple-mobile-web-app-capable" content="yes" />
      </head>
      <body>
        <ProjectTargetHighlighter />
        {children}
      </body>
    </html>
  );
}
