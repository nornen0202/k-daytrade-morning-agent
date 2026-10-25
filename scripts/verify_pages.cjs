const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

(async () => {
  const base = process.argv[2] || pathToFileURL(path.resolve("dist/index.html")).href;
  const output = path.resolve("private_artifacts/pages-review");
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const checks = [];
  try {
    for (const width of [390, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      await page.goto(base);
      await page.screenshot({ path: path.join(output, "home-" + width + ".png"), fullPage: true });
      const home = await page.evaluate(() => ({
        width: innerWidth, scroll: document.documentElement.scrollWidth,
        currentCandidateVisible: !!document.getElementById("current-brief"),
        notice: document.getElementById("freshness-notice").textContent,
        lastGenerated: document.querySelector(".context-grid").textContent,
      }));
      if (home.scroll > width) throw Error("Home overflow at " + width);
      if (home.currentCandidateVisible) throw Error("Unexpected current research on closed day");
      await page.locator(".context-grid a").first().click();
      await page.screenshot({ path: path.join(output, "report-" + width + ".png"), fullPage: true });
      const detail = await page.evaluate(() => ({
        title: document.querySelector("h1").textContent,
        scroll: document.documentElement.scrollWidth,
        candidates: document.querySelectorAll("table").length,
      }));
      if (detail.scroll > width || detail.candidates) throw Error("Notice leaks candidate table");
      checks.push({ width, home, detail });
      await page.close();
    }
    fs.writeFileSync(path.join(output, "browser-checks.json"), JSON.stringify(checks, null, 2));
    console.log(JSON.stringify(checks, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
