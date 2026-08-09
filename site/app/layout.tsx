import type { Metadata } from 'next';
import './globals.css';

const description =
  'I build agent systems that can prove what they did. One-person applied research practice: multi-agent harnesses, adversarial evaluation, evidence extraction — shipped as working code, in public.';

export const metadata: Metadata = {
  metadataBase: new URL('https://grahama.co'),
  title: 'Graham Anderson — agent systems that prove what they did',
  description,
  openGraph: {
    title: 'Graham Anderson — agent systems that prove what they did',
    description,
    url: 'https://grahama.co',
    siteName: 'grahama.co',
    type: 'website',
    images: [{ url: '/og.png', width: 1200, height: 630, alt: 'grahama.co — G꜀ mark, agent systems that prove what they did' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Graham Anderson — agent systems that prove what they did',
    description,
    images: ['/og.png'],
  },
};


export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Preload the display face so the largest text (LCP) paints without a
            late font discovery. Variable cuts are the only display fonts. */}
        <link
          rel="preload"
          href="/fonts/literata-latin-var.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
      </head>
      <body>
        {children}
      </body>
    </html>
  );
}
