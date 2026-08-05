/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  // Project-pages path (grahama1970.github.io/agent-skills) until a custom
  // domain is attached; the deploy workflow sets this, local dev leaves it "".
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || '',
  images: { unoptimized: true },
};

export default nextConfig;
