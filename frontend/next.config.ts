import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Operator UI talks to FastAPI on loopback; no secrets in the bundle.
};

export default nextConfig;
