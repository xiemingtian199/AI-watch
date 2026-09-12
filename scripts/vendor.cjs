const fs = require("node:fs");
const path = require("node:path");
const target = path.join(__dirname, "../app/vendor");
fs.mkdirSync(target, { recursive: true });
for (const [source, name] of [
  ["chart.js/dist/chart.umd.js", "chart.umd.js"],
  ["chart.js/LICENSE.md", "chart.LICENSE.md"],
  ["lucide/dist/umd/lucide.js", "lucide.js"],
  ["lucide/LICENSE", "lucide.LICENSE"],
])
  fs.copyFileSync(
    path.join(__dirname, "../node_modules", source),
    path.join(target, name),
  );
console.log("Vendored browser libraries for offline use.");
