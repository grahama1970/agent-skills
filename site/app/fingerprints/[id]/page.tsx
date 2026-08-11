import type { Metadata } from 'next';
import { FingerprintReview } from '@/components/fingerprint-review';
import { getFingerprintIds } from '@/lib/fingerprint';

export const dynamic = 'force-static';
export const dynamicParams = false;

export const metadata: Metadata = {
  title: 'grahama.co fingerprint candidate',
  robots: { index: false, follow: false },
};

export function generateStaticParams() {
  return getFingerprintIds().map((id) => ({ id }));
}

export default async function FingerprintIdPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <FingerprintReview requestedId={id} />;
}
