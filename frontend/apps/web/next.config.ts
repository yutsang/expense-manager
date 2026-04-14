import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@aegis/ui", "@aegis/api-client", "@aegis/money", "@aegis/types"],
  async rewrites() {
    // In dev, proxy /api/* to the FastAPI backend on port 8000
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
