import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A production build can live next to the dev server's .next (NEXT_DIST_DIR=.next-prod).
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
