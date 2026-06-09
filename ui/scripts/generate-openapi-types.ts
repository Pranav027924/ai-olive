/**
 * Generate TS types from the chat-service and dashboard-service
 * OpenAPI specs. Both services have to be running locally — typical
 * dev loop: `make up && make migrate-all && uv run uvicorn ...`.
 */
import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

interface Target {
  name: string;
  url: string;
  out: string;
}

const targets: Target[] = [
  {
    name: "chat",
    url: process.env.CHAT_OPENAPI_URL ?? "http://127.0.0.1:8001/openapi.json",
    out: "src/api/__generated__/chat.ts",
  },
  {
    name: "dashboard",
    url: process.env.DASHBOARD_OPENAPI_URL ?? "http://127.0.0.1:8004/openapi.json",
    out: "src/api/__generated__/dashboard.ts",
  },
];

const outDir = resolve("src/api/__generated__");
mkdirSync(outDir, { recursive: true });

for (const target of targets) {
  console.log(`[openapi] generating ${target.name} from ${target.url}`);
  execSync(`npx openapi-typescript "${target.url}" -o "${target.out}"`, {
    stdio: "inherit",
  });
}
