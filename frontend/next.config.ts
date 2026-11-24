import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // small self-contained server for Docker
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
