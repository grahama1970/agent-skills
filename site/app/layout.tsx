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
    images: [{ url: '/dream/dream-panel.webp', width: 1600, height: 1067 }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Graham Anderson — agent systems that prove what they did',
    description,
    images: ['/dream/dream-panel.webp'],
  },
};


export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        
        {children}
      </body>
    </html>
  );
}
