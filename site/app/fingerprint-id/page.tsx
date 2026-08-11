import type { Metadata } from 'next';
import { FingerprintReview } from '@/components/fingerprint-review';

export const dynamic = 'force-static';

export const metadata: Metadata = {
  title: 'grahama.co fingerprint candidate',
  robots: { index: false, follow: false },
};

export default function FingerprintIdPage() {
  return <FingerprintReview requestedId="fingerprint-id" />;
}
