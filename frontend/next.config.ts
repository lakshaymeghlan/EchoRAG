import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export -> an `out/` folder of plain HTML/JS that FastAPI serves
  // directly, so the UI and the API share one origin and one URL.
  output: "export",

  // The export has no Node server to optimise images on the fly.
  images: { unoptimized: true },

  // Emit /ask/index.html style paths so static hosts resolve routes without
  // server-side rewrites.
  trailingSlash: true,
};

export default nextConfig;
