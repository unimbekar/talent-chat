import path from "path";
import type { NextConfig } from "next";

const api = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.join(__dirname),
  experimental: {
    // Above the API's worst model wait: two 90-second attempts when a saved job description is read.
    proxyTimeout: 200_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
