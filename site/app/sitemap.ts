import type { MetadataRoute } from 'next';

export const dynamic = 'force-static';

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: 'https://grahama.co',
      changeFrequency: 'monthly',
      priority: 1,
    },
    {
      url: 'https://grahama.co/resume',
      changeFrequency: 'monthly',
      priority: 0.8,
    },
    {
      url: 'https://grahama.co/explore',
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: 'https://grahama.co/ledger',
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: 'https://grahama.co/how-proof-works',
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: 'https://grahama.co/fingerprint',
      changeFrequency: 'weekly',
      priority: 0.1,
    },
  ];
}
