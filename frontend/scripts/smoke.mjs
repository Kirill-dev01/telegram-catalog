// HTTP checks against the production Next build with a fixture API.
// This verifies SSR states, not Telegram or the real backend.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
let productName = "Проверочная кружка";
const api = createServer((req, res) => {
  const query = new URL(req.url, "http://test").searchParams.get("q");
  res.setHeader("Content-Type", "application/json");
  if (query === "offline") {
    res.writeHead(503).end(JSON.stringify({ detail: "Unavailable" }));
  } else {
    res.end(JSON.stringify({
      items: query === "empty" ? [] : [{ id: 1, name: productName,
        image_url: "/api/products/1/image", created_at: "2026-10-26T00:00:00Z" }],
      next_cursor: null,
    }));
  }
});
await new Promise(resolve => api.listen(0, "127.0.0.1", resolve));
const apiPort = api.address().port;
const probe = createServer();
await new Promise(resolve => probe.listen(0, "127.0.0.1", resolve));
const port = probe.address().port;
await new Promise(resolve => probe.close(resolve));
const child = spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "-p", String(port), "-H", "127.0.0.1"], {
  cwd: root,
  env: { ...process.env, API_BASE_URL: `http://127.0.0.1:${apiPort}`, NEXT_TELEMETRY_DISABLED: "1" },
  stdio: ["ignore", "pipe", "pipe"],
});
let log = "";
child.stdout.on("data", data => { log += data; });
child.stderr.on("data", data => { log += data; });
const base = `http://127.0.0.1:${port}`;
try {
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const response = await fetch(base + "/health/live", { signal: AbortSignal.timeout(1000) });
      if (response.ok) { ready = true; break; }
    } catch {}
    if (child.exitCode !== null) throw new Error(log);
    await delay(250);
  }
  assert(ready, "Next server did not become ready: " + log);
  let response = await fetch(base);
  assert.equal(response.status, 200);
  let html = await response.text();
  assert(html.includes("Проверочная кружка"));
  assert(html.includes('lang="ru"'));
  assert(html.includes("/api/products/1/image"));
  assert(response.headers.get("cache-control")?.includes("no-store"));
  productName = "Обновлённый товар";
  html = await (await fetch(base)).text();
  assert(html.includes("Обновлённый товар"), "A fresh SSR request must see fresh API data");
  html = await (await fetch(base + "/?q=empty")).text();
  assert(html.includes("Ничего не найдено"));
  html = await (await fetch(base + "/?q=offline")).text();
  assert(html.includes("Каталог временно недоступен"));
  assert(!html.includes("Пока нет товаров"));
  console.log("Frontend HTTP smoke passed: product rendering, fresh data, search empty state, API error state.");
} finally {
  child.kill("SIGTERM");
  await new Promise(resolve => api.close(resolve));
}
