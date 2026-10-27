import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  cacheMaxMemorySize: 0,
  images: { unoptimized: true },
  async rewrites() {
    // Useful for `npm run dev`; Compose sends /api directly to FastAPI.
    return [{
      source: "/api/:path*",
      destination: `${process.env.API_BASE_URL || "http://api:8000"}/api/:path*`,
    }];
  },
};

export default nextConfig;
