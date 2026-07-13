/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: emits a static `out/` bundle that any static host or CDN can serve.
  output: 'export',
  reactStrictMode: true,
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
