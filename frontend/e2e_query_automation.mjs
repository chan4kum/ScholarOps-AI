import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = "http://127.0.0.1:5173";
const QUERY = "funded PhD in AI Machine learning Data Science Europe";
const SCREENSHOT_DIR = path.resolve("./screenshots/query_run");

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function runQueryAutomation() {
  console.log("=================================================");
  console.log(`🎯 Executing End-to-End Query Automation`);
  console.log(`Query: "${QUERY}"`);
  console.log(`Target: ${BASE_URL}`);
  console.log("=================================================");

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  try {
    // 1. Navigate to App
    console.log("\n[Step 1] Loading ScholarOps AI Dashboard...");
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.waitForTimeout(1000);

    // 2. Test Advisor Chat with Target Query
    console.log("\n[Step 2] Sending Query to Advisor Chat Agent...");
    await page.click("nav.tabs button:has-text('Advisor')");
    await page.waitForTimeout(600);

    const chatTextarea = page.locator("textarea");
    if (await chatTextarea.isVisible()) {
      await chatTextarea.fill(QUERY);
      console.log(` Filled chat input with: "${QUERY}"`);
      await page.click("button:has-text('Send')");
      console.log(" Sent message, waiting for Advisor response...");
      // Wait for chat to update
      await page.waitForTimeout(6000);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "step2_advisor_response.png"), fullPage: true });
      console.log(" Saved screenshot: step2_advisor_response.png");
    }

    // 3. Test Opportunities Discovery with Target Query
    console.log("\n[Step 3] Running Discovery for Target Query...");
    await page.click("nav.tabs button:has-text('Opportunities')");
    await page.waitForTimeout(600);

    const discoveryInput = page.locator(".search-row input");
    if (await discoveryInput.isVisible()) {
      await discoveryInput.fill(QUERY);
      await page.click(".search-row button:has-text('Discover')");
      console.log(" Discovery triggered, waiting for sources to aggregate...");
      await page.waitForTimeout(6000);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "step3_discovery_results.png"), fullPage: true });
      console.log(" Saved screenshot: step3_discovery_results.png");
    }

    // 4. Test RAG Studio Hybrid Search with Target Query
    console.log("\n[Step 4] Running RAG Studio Hybrid Search & Cross-Encoder Reranker...");
    await page.click("nav.tabs button:has-text('RAG & KG Studio')");
    await page.waitForTimeout(600);

    const searchInput = page.locator("input[placeholder*='search query']");
    if (await searchInput.isVisible()) {
      await searchInput.fill(QUERY);
      await page.click("button:has-text('Run Hybrid Search')");
      console.log(" Hybrid search & reranker executing...");
      await page.waitForTimeout(4000);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "step4_hybrid_search_results.png"), fullPage: true });
      console.log(" Saved screenshot: step4_hybrid_search_results.png");
    }

    // 5. Test Self-Improving RAG Generation with Target Query
    console.log("\n[Step 5] Running Self-Improving RAG (CRAG) & LLM-as-a-Judge...");
    await page.click("button:has-text('2. Self-Improving RAG')");
    await page.waitForTimeout(600);

    const genInput = page.locator("input[placeholder*='synthesize']");
    if (await genInput.isVisible()) {
      await genInput.fill(`Draft statement of fit for: ${QUERY}`);
      await page.click("button:has-text('Generate with CRAG')");
      console.log(" CRAG generation & fact-checking judge running...");
      await page.waitForTimeout(10000);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "step5_crag_generation_judge.png"), fullPage: true });
      console.log(" Saved screenshot: step5_crag_generation_judge.png");
    }

    console.log("\n=================================================");
    console.log("🎉 ALL PLAYWRIGHT QUERY AUTOMATION STEPS COMPLETED!");
    console.log("=================================================");
  } catch (err) {
    console.error("❌ Automation Error:", err);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "error_screenshot.png"), fullPage: true });
  } finally {
    await browser.close();
  }
}

runQueryAutomation();
