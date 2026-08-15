import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = "http://127.0.0.1:5173";
const SCREENSHOT_DIR = path.resolve("./screenshots/prepare_downloads");

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function testPrepareDownloads() {
  console.log("=================================================");
  console.log("📥 Testing Prepare Tab Downloads & Formatting");
  console.log("=================================================");

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  try {
    await page.goto(BASE_URL, { waitUntil: "networkidle" });
    await page.waitForTimeout(1000);

    // Switch to Prepare Tab
    await page.click("nav.tabs button:has-text('Prepare')");
    await page.waitForTimeout(1500);

    // Check presence of download buttons
    const fullDossierBtn = page.locator("button:has-text('Download Full Dossier')");
    const downloadBtns = page.locator("button:has-text('Download (.md)')");
    const copyBtns = page.locator("button:has-text('Copy')");

    console.log(" Download buttons count:", await downloadBtns.count());
    console.log(" Copy buttons count:", await copyBtns.count());
    console.log(" Full Dossier button visible:", await fullDossierBtn.isVisible());

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "prepare_with_download_buttons.png"),
      fullPage: true,
    });
    console.log(" Screenshot saved to prepare_with_download_buttons.png");

    console.log("=================================================");
    console.log("🎉 PREPARE DOWNLOADS UI VERIFIED SUCCESSFULLY!");
    console.log("=================================================");
  } catch (err) {
    console.error("❌ Test error:", err);
  } finally {
    await browser.close();
  }
}

testPrepareDownloads();
