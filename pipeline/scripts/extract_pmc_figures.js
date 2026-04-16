#!/usr/bin/env node
// extract_pmc_figures.js — Screenshot individual figures from a PMC article
//
// Usage: node extract_pmc_figures.js <PMCID> <output_dir>
// Example: node extract_pmc_figures.js PMC3214617 /tmp/annotate-paper/17463248
//
// Navigates to the PMC article page, finds all figure elements,
// screenshots each one individually, and extracts caption text.
//
// Requires: npm install -D playwright && npx playwright install chromium

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function extractFigures(pmcid, outputDir) {
  if (!pmcid.startsWith('PMC')) {
    console.error(`Error: Expected PMC ID (e.g., PMC2847889), got: ${pmcid}`);
    console.error('Convert PMID to PMCID first using convert_article_ids MCP tool.');
    process.exit(1);
  }

  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const url = `https://www.ncbi.nlm.nih.gov/pmc/articles/${pmcid}/`;
  console.log(`Navigating to: ${url}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ResearchShop-Benchmark/1.0'
  });
  const page = await context.newPage();

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });

    // Check for "article not found" or redirect
    const title = await page.title();
    if (title.includes('Page not found') || title.includes('Error')) {
      console.error(`Article not found at ${url}`);
      process.exit(1);
    }

    // PMC uses several figure container patterns depending on article age/format
    const selectors = [
      'figure.fig',                // Modern PMC HTML5
      'div.fig',                   // Classic PMC
      'figure',                    // Generic HTML5 fallback
    ];

    let figures = [];
    let usedSelector = '';
    for (const sel of selectors) {
      const found = await page.$$(sel);
      if (found.length > 0) {
        figures = found;
        usedSelector = sel;
        break;
      }
    }

    if (figures.length === 0) {
      console.log(JSON.stringify({ figures: 0, files: [], message: 'No figures found on page' }));
      await browser.close();
      return;
    }

    console.log(`Found ${figures.length} figures using selector: ${usedSelector}`);

    const results = [];

    for (let i = 0; i < figures.length; i++) {
      const num = String(i + 1).padStart(2, '0');
      const pngPath = path.join(outputDir, `figure_${num}.png`);

      // Screenshot the figure element
      try {
        await figures[i].scrollIntoViewIfNeeded();

        // Wait for lazy-loaded images inside this figure to render.
        // PMC uses loading="lazy" and sometimes wraps images in <a> links.
        // Strategy: find all <img> in the figure, wait for each to have a
        // naturalWidth > 0 (meaning the image data has loaded).
        await page.waitForTimeout(500);
        const imgCount = await figures[i].$$eval('img', imgs => imgs.length);
        if (imgCount > 0) {
          try {
            await figures[i].$$eval('img', imgs => {
              // Remove lazy loading to force immediate load
              imgs.forEach(img => {
                img.removeAttribute('loading');
                // If data-src exists (common lazy-load pattern), copy to src
                if (img.dataset.src && !img.src) {
                  img.src = img.dataset.src;
                }
              });
            });
            // Wait for at least one image to have non-zero dimensions
            await page.waitForFunction(
              (figEl) => {
                const imgs = figEl.querySelectorAll('img');
                return Array.from(imgs).some(img => img.naturalWidth > 0 && img.complete);
              },
              figures[i],
              { timeout: 8000 }
            );
            // Extra settle time for rendering
            await page.waitForTimeout(300);
          } catch {
            // Timeout waiting for images — screenshot whatever we have
            console.error(`Warning: Figure ${i + 1} images may not have fully loaded`);
          }
        } else {
          // No <img> tags — might be an SVG, canvas, or iframe figure
          await page.waitForTimeout(1000);
        }

        await figures[i].screenshot({ path: pngPath });
      } catch (err) {
        console.error(`Warning: Could not screenshot figure ${i + 1}: ${err.message}`);
        continue;
      }

      // Extract caption text from various caption selectors
      let caption = '';
      const captionSelectors = ['figcaption', '.caption', '.fig-caption', '.caption-text'];
      for (const cs of captionSelectors) {
        try {
          caption = await figures[i].$eval(cs, el => el?.textContent?.trim() || '');
          if (caption) break;
        } catch {
          // selector not found, try next
        }
      }

      // Extract figure label (e.g., "Figure 1", "Fig. 2")
      let label = '';
      try {
        label = await figures[i].$eval('.label, .fig-label, strong', el => el?.textContent?.trim() || '');
      } catch {
        // no label element
      }

      // Save caption to text file
      if (caption || label) {
        const captionPath = path.join(outputDir, `figure_${num}_caption.txt`);
        const captionContent = [label, caption].filter(Boolean).join('\n');
        fs.writeFileSync(captionPath, captionContent);
      }

      const fileSize = fs.statSync(pngPath).size;
      results.push({
        index: i + 1,
        file: `figure_${num}.png`,
        size_kb: Math.round(fileSize / 1024),
        label: label || `Figure ${i + 1}`,
        has_caption: !!caption,
        caption_preview: caption ? caption.substring(0, 100) + (caption.length > 100 ? '...' : '') : ''
      });
    }

    // Output structured summary
    console.log(JSON.stringify({ figures: results.length, files: results }, null, 2));
  } catch (err) {
    console.error(`Error: ${err.message}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

// --- CLI entry point ---
const [,, pmcid, outputDir] = process.argv;
if (!pmcid || !outputDir) {
  console.error('Usage: node extract_pmc_figures.js <PMCID> <output_dir>');
  console.error('Example: node extract_pmc_figures.js PMC3214617 /tmp/figures');
  process.exit(1);
}

extractFigures(pmcid, outputDir);
