import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  experimental: {
    cpus: 1,
    useTypeScriptCli: true,
  },
};

export default nextConfig;
