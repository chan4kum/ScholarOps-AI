import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = "http://127.0.0.1:5173";
const VIDEO_DIR = path.resolve("./videos");

if (!fs.existsSync(VIDEO_DIR)) {
  fs.mkdirSync(VIDEO_DIR, { recursive: true });
}

async function recordLiveBrowserAutomation() {
  console.log("=================================================");
  console.log("🎥 Recording Live Browser Automation Session");
  console.log(`Target URL: ${BASE_URL}`);
  console.log(`Video Output Directory: ${VIDEO_DIR}`);
  console.log("=================================================");

  const browser = await chromium.launch({
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: {
      dir: VIDEO_DIR,
      size: { width: 1280, height: 720 },
    },
  });

  const page = await context.newPage();

  try {
    // 1. Documents Tab
    console.log("-> 1. Documents Ingestion Dashboard...");
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.waitForTimeout(2000);
    await page.evaluate(() => window.scrollBy(0, 300));
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(1000);

    // 2. Advisor Tab
    console.log("-> 2. Candidate Profile & AI/DS/ML Advisor...");
    await page.click("nav.tabs button:has-text('Advisor')");
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.scrollBy(0, 400));
    await page.waitForTimeout(2000);
    await page.evaluate(() => window.scrollBy(0, 400));
    await page.waitForTimeout(1500);

    // Chat interaction
    console.log("-> 3. Interacting with Advisor Chat...");
    const textarea = page.locator("textarea");
    if (await textarea.isVisible()) {
      await textarea.fill("What are my top recommended PhD research directions in Europe across AI, Data Science and Machine Learning?");
      await page.waitForTimeout(1000);
      await page.click("button:has-text('Send')");
      await page.waitForTimeout(5000);
    }

    // 3. Opportunities Tab
    console.log("-> 4. Opportunities Discovery & Shortlist...");
    await page.click("nav.tabs button:has-text('Opportunities')");
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.scrollBy(0, 300));
    await page.waitForTimeout(1000);

    // Toggle star shortlist
    const starBtn = page.locator(".star-btn").first();
    if (await starBtn.isVisible()) {
      await starBtn.click();
      await page.waitForTimeout(1000);
    }

    // 4. Prepare Tab
    console.log("-> 5. Application Dossier (CV, Cover Letter, Proposal)...");
    await page.click("nav.tabs button:has-text('Prepare')");
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.scrollBy(0, 400));
    await page.waitForTimeout(1500);

    // 5. Apply Tab (HITL Gate)
    console.log("-> 6. Human-in-the-Loop (HITL) Gate...");
    await page.click("nav.tabs button:has-text('Apply')");
    await page.waitForTimeout(2000);

    // 6. RAG & KG Studio
    console.log("-> 7. Production RAG Studio (Hybrid Search + Cross-Encoder)...");
    await page.click("nav.tabs button:has-text('RAG & KG Studio')");
    await page.waitForTimeout(1500);

    // Run Hybrid Search
    console.log("-> 8. Triggering Hybrid Search & LLM Reranker...");
    await page.click("button:has-text('Run Hybrid Search')");
    await page.waitForTimeout(3000);
    await page.evaluate(() => window.scrollBy(0, 400));
    await page.waitForTimeout(2000);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(1000);

    // Switch to Self-Improving RAG
    console.log("-> 9. Self-Improving RAG (Judge Scorecards)...");
    await page.click("button:has-text('2. Self-Improving RAG')");
    await page.waitForTimeout(1500);
    await page.click("button:has-text('Generate with CRAG')");
    await page.waitForTimeout(6000);
    await page.evaluate(() => window.scrollBy(0, 400));
    await page.waitForTimeout(2000);

    // Switch to Google LangGraph Workflow
    console.log("-> 10. Google LangGraph Workflow Runner...");
    await page.click("button:has-text('3. Google LangGraph')");
    await page.waitForTimeout(2000);

    console.log("=================================================");
    console.log("✨ Live Browser Automation Session Finished!");
    console.log("=================================================");
  } catch (err) {
    console.error("❌ Recording Error:", err);
  } finally {
    const videoPath = await page.video()?.path();
    await page.close();
    await context.close();
    await browser.close();

    if (videoPath && fs.existsSync(videoPath)) {
      const finalDest = path.join(VIDEO_DIR, "scholarops_live_automation.webm");
      fs.copyFileSync(videoPath, finalDest);
      console.log(`🎬 Video recording successfully saved to: ${finalDest}`);
    }
  }
}

recordLiveBrowserAutomation();
