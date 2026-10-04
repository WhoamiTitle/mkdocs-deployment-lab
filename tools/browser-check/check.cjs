// Exercise the real Material search worker with external origins blocked.
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");

async function main() {
  const directory = path.resolve(process.argv[2] || "site");
  const output = process.argv[3];
  const cases = JSON.parse(fs.readFileSync("config/search-cases.json", "utf8"));
  const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
  const server = http.createServer((request, response) => {
    let relative = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
    if (relative.endsWith("/")) relative += "index.html";
    const file = path.resolve(directory, "." + relative);
    if (!file.startsWith(directory + path.sep) || !fs.existsSync(file)) {
      response.writeHead(404).end();
      return;
    }
    response.setHeader("Content-Type", (types[path.extname(file)] || "application/octet-stream") + "; charset=utf-8");
    response.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
    const context = await browser.newContext();
    const external = [];
    await context.route("**/*", route => {
      if (new URL(route.request().url()).origin === origin) return route.continue();
      external.push(route.request().url());
      return route.abort();
    });
    const versions = fs.existsSync(path.join(directory, "versions.json"))
      ? JSON.parse(fs.readFileSync(path.join(directory, "versions.json"), "utf8")) : [];
    const newest = versions.find(entry => entry.aliases.includes("latest"));
    const prefix = newest ? `/${newest.version}/` : "/";
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("response", response => { if (response.status() >= 400) errors.push(`HTTP ${response.status()}: ${response.url()}`); });
    await page.goto(origin + prefix);
    const index = JSON.parse(fs.readFileSync(path.join(directory, prefix, "search/search_index.json"), "utf8"));
    const corpus = index.docs.map(document => document.title + " " + document.text).join(" ");
    for (const item of cases) {
      const exact = new RegExp(`(?<![А-Яа-яЁё])${item.query}(?![А-Яа-яЁё])`, "iu");
      if (exact.test(corpus)) throw new Error(`Search query already occurs verbatim in the index: ${item.query}`);
    }
    await page.locator('#__search').evaluate(element => { element.checked = true; element.dispatchEvent(new Event("change", { bubbles: true })); });
    await page.locator('[data-md-component="search-query"]').focus();
    await page.waitForTimeout(2000);
    const results = [];
    for (const item of cases) {
      const input = page.locator('[data-md-component="search-query"]');
      await input.fill("");
      await input.pressSequentially(item.query, { delay: 40 });
      await input.press("ArrowRight");
      const links = page.locator('[data-md-component="search-result"] a');
      await page.waitForTimeout(700);
      const hrefs = await links.evaluateAll(elements => elements.map(element => element.getAttribute("href")));
      const locations = hrefs.filter(Boolean).map(href => new URL(href, page.url()).pathname);
      const passed = locations.includes(prefix + (item.page === "index.html" ? "" : item.page));
      results.push({ ...item, passed, matches: new Set(locations).size, locations: [...new Set(locations)] });
    }
    if (newest) {
      await page.goto(origin + "/");
      await page.waitForURL(origin + `/${newest.version}/`);
      const selector = page.locator('.md-version');
      await selector.waitFor();
      await page.waitForFunction(count => document.querySelectorAll('.md-version__link').length >= count, versions.length);
      const text = await selector.textContent();
      for (const version of versions) {
        if (!text.includes(version.title)) throw new Error(`Missing version switcher entry: ${version.title}`);
      }
      // Follow an actual switcher link to a different version.
      const other = versions.find(entry => entry.version !== newest.version);
      if (other) {
        const link = selector.locator("a").filter({ hasText: other.title }).first();
        await link.evaluate(element => element.click());
        await page.waitForURL(origin + `/${other.version}/`);
      }
    }
    const report = { search_language: "ru,en", version_switcher: Boolean(newest), external_requests: external, browser_errors: errors, results };
    if (output) fs.writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify(report, null, 2));
    if (external.length || errors.length || results.some(result => !result.passed)) throw new Error("Local search or external resource check failed");
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
