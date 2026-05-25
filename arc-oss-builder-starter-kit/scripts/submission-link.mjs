import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync("package.json", "utf8"));
const packageRepo = pkg.repository?.url?.replace(/^git\+/, "").replace(/\.git$/, "");
const packageDirectory = pkg.repository?.directory;
const repo =
  process.env.ARC_OSS_REPO_URL ||
  (packageRepo && packageDirectory ? `${packageRepo}/tree/main/${packageDirectory}` : undefined) ||
  "https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation/tree/main/arc-oss-builder-starter-kit";

console.log("Arc OSS starter kit folder:");
console.log(repo);
console.log("");
console.log("Paste this link into the Arc OSS submission form / CLI update.");
