/** @type {import('next').NextConfig} */
const config = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    const target = process.env.INTERNAL_API_URL || "http://api:8000";
    return [{ source: "/api/:path*", destination: `${target}/api/:path*` }];
  },
  experimental: {
    // Single-user local app — disable the client-side Router Cache so navigating
    // between pages always refetches fresh Server Component data.
    // Without this, edits to categories/accounts/etc. at one page don't reflect on
    // others (e.g. dashboard) until the cache expires (~30s for dynamic routes).
    staleTimes: {
      dynamic: 0,
      static: 0,
    },
  },
};
export default config;
