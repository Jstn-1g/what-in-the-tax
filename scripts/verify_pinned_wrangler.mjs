#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

function readJson(relativePath) {
  return JSON.parse(readFileSync(join(root, relativePath), "utf8"));
}

const manifest = readJson("package.json");
const lock = readJson("package-lock.json");
const installed = readJson("node_modules/wrangler/package.json");

const expected = manifest.devDependencies?.wrangler;
const lockRequest = lock.packages?.[""]?.devDependencies?.wrangler;
const lockVersion = lock.packages?.["node_modules/wrangler"]?.version;

if (typeof expected !== "string" || !/^\d+\.\d+\.\d+$/.test(expected)) {
  throw new Error("package.json must exact-pin Wrangler to a stable x.y.z release");
}

for (const [source, value] of [
  ["package-lock root request", lockRequest],
  ["package-lock resolved package", lockVersion],
  ["installed package", installed.version],
]) {
  if (value !== expected) {
    throw new Error(`${source} has Wrangler ${String(value)}; expected ${expected}`);
  }
}

console.log(`Verified exact Wrangler ${expected}`);
