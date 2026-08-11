import type { Metadata } from 'next';
import { FingerprintReview } from '@/components/fingerprint-review';

export const dynamic = 'force-static';

export const metadata: Metadata = {
  title: 'grahama.co public fingerprint review',
  robots: { index: false, follow: false },
};

export default function FingerprintPage() {
  return <FingerprintReview />;
}
