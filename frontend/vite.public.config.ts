import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

function publicIngressGuard(): Plugin {
  return {
    name: "public-ingress-guard",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = (request.url ?? "/").split("?", 1)[0];
        if (pathname === "/api/v1/edge" || pathname.startsWith("/api/v1/edge/")) {
          response.statusCode = 403;
          response.setHeader("Content-Type", "application/json; charset=utf-8");
          response.end(JSON.stringify({
            schema_version: "1.0",
            error: {
              code: "PUBLIC_EDGE_WRITE_BLOCKED",
              message: "Edge write routes are not exposed by the public demo.",
              details: {},
              request_id: "public-demo-proxy",
            },
          }));
          return;
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [publicIngressGuard(), react()],
  define: {
    "import.meta.env.VITE_API_MODE": JSON.stringify("real"),
    "import.meta.env.VITE_API_BASE_URL": JSON.stringify(""),
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (proxyRequest) => {
            proxyRequest.setHeader("origin", "http://127.0.0.1:5173");
          });
        },
      },
    },
  },
});
