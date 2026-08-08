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
  ];
}
