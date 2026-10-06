import type { NextConfig } from "next";

// The browser always talks to the frontend origin; /api/* is proxied to the FastAPI
// service. next.config is serialized at build time, so the Docker image receives this
// URL as a build argument.
const apiUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
