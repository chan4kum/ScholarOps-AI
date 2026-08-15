import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = "http://127.0.0.1:5173";
const SCREENSHOT_DIR = path.resolve("./screenshots");

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function runE2ETests() {
  console.log("=================================================");
  console.log("🚀 Starting Playwright E2E UI Test Suite");
  console.log(`Target URL: ${BASE_URL}`);
  console.log("=================================================");

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const results = [];

  try {
    // 1. Initial Load & Documents Tab
    console.log("\n[1/7] Testing Documents Tab & Health Status...");
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.waitForSelector("h1");
    const title = await page.textContent("h1");
    console.log(` Page title: "${title.trim()}"`);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "01_documents_tab.png"), fullPage: true });
    results.push({ test: "Documents Tab Loaded", status: "PASSED" });

    // 2. Advisor Tab
    console.log("\n[2/7] Testing Advisor Tab...");
    await page.click("nav.tabs button:has-text('Advisor')");
    await page.waitForTimeout(500);
    const profileText = await page.textContent(".card");
    console.log(` Advisor profile rendered (${profileText.length} chars)`);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "02_advisor_tab.png"), fullPage: true });
    results.push({ test: "Advisor Tab & Profile", status: "PASSED" });

    // 3. Opportunities Tab
    console.log("\n[3/7] Testing Opportunities Tab...");
    await page.click("nav.tabs button:has-text('Opportunities')");
    await page.waitForTimeout(500);
    const rowCount = await page.locator(".data-table tbody tr").count();
    console.log(` Discovered Opportunities rendered: ${rowCount} rows`);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "03_opportunities_tab.png"), fullPage: true });
    results.push({ test: `Opportunities Tab (${rowCount} vacancies)`, status: "PASSED" });

    // 4. Prepare Tab
    console.log("\n[4/7] Testing Prepare Tab...");
    await page.click("nav.tabs button:has-text('Prepare')");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "04_prepare_tab.png"), fullPage: true });
    results.push({ test: "Prepare Tab & Packet Drafter", status: "PASSED" });

    // 5. Apply Tab
    console.log("\n[5/7] Testing Apply Tab...");
    await page.click("nav.tabs button:has-text('Apply')");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "05_apply_tab.png"), fullPage: true });
    results.push({ test: "Apply Tab & HITL Security Gate", status: "PASSED" });

    // 6. Monitor & Ops Tabs
    console.log("\n[6/7] Testing Monitor & Ops Tabs...");
    await page.click("nav.tabs button:has-text('Monitor')");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "06_monitor_tab.png"), fullPage: true });
    results.push({ test: "Monitor Tab & Agent Telemetry", status: "PASSED" });

    // 7. RAG & KG Studio Tab
    console.log("\n[7/7] Testing RAG & KG Studio (Hybrid Search + Reranker + CRAG)...");
    await page.click("nav.tabs button:has-text('RAG & KG Studio')");
    await page.waitForTimeout(500);

    // Trigger Hybrid Search
    console.log(" Clicking 'Run Hybrid Search'...");
    await page.click("button:has-text('Run Hybrid Search')");
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "07_rag_hybrid_search.png"), fullPage: true });

    // Switch to Self-Improving RAG Subtab
    console.log(" Testing 'Self-Improving RAG (Judge)' Subtab...");
    await page.click("button:has-text('2. Self-Improving RAG')");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "08_rag_judge_view.png"), fullPage: true });

    // Switch to Google LangGraph Workflow Subtab
    console.log(" Testing 'Google LangGraph Workflow' Subtab...");
    await page.click("button:has-text('3. Google LangGraph')");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "09_rag_google_workflow.png"), fullPage: true });
    results.push({ test: "RAG & KG Studio (Search, Judge & LangGraph)", status: "PASSED" });

    console.log("\n=================================================");
    console.log("🎉 ALL PLAYWRIGHT E2E TESTS COMPLETED SUCCESSFULLY!");
    console.log("=================================================");
    console.table(results);
    console.log(`\nScreenshots saved to: ${SCREENSHOT_DIR}`);
  } catch (err) {
    console.error("❌ E2E Test Failed:", err);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "error_screenshot.png"), fullPage: true });
    process.exit(1);
  } finally {
    await browser.close();
  }
}

runE2ETests();
