# Frontend placeholder for Phase 1.
# Full Next.js app is created in Phase 7.
# Optional compose profile: docker compose --profile frontend up

FROM node:20-alpine

WORKDIR /app

# Minimal placeholder server so the optional frontend service can start.
RUN printf '%s\n' \
  'const http = require("http");' \
  'const port = process.env.PORT || 3000;' \
  'http.createServer((req, res) => {' \
  '  res.writeHead(200, {"Content-Type": "text/plain; charset=utf-8"});' \
  '  res.end("Frontend placeholder — Next.js UI arrives in Phase 7\\n");' \
  '}).listen(port, () => console.log(`listening on ${port}`));' \
  > server.js

EXPOSE 3000
CMD ["node", "server.js"]
