import * as cheerio from "cheerio";
import fs from "fs";
import path from "path";

const REGIONS = ["R1", "R2", "R3"];
const CURRENT_YEAR = new Date().getFullYear();
const COMMAND_ARGS = process.argv.slice(2);
const IS_DELTA = COMMAND_ARGS.includes("--delta");

const START_YEAR = IS_DELTA ? CURRENT_YEAR : 1998;
const END_YEAR = CURRENT_YEAR;
const DELAY_MS = 500; // Polite delay between requests to avoid blocks

const outputDir = path.resolve(process.cwd(), "data");

// Ensure output directory exists
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

interface EonrRecord {
  year: number;
  date: string;
  area: string;
  title: string;
  url: string;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function scrapeHistoricEmergencyOrders() {
  console.log(`🎣 Initializing Historic ADF&G EONR Mass-Scraper...`);
  console.log(`🛠️ Mode: ${IS_DELTA ? "DELTA (Current Year Only)" : "FULL ARCHIVE (1998-Current)"}`);
  console.log(`📅 Target Range: ${START_YEAR} - ${END_YEAR}`);
  console.log(`🌐 Target Regions: ${REGIONS.join(", ")}\n`);

  for (const region of REGIONS) {
    console.log(`\n========================================`);
    console.log(`📍 Processing Region: ${region}`);
    console.log(`========================================`);
    
    // Load existing mapping if in delta mode to prevent losing history
    const outputPath = path.join(outputDir, `${region}.json`);
    let regionOrders: EonrRecord[] = [];
    
    if (IS_DELTA && fs.existsSync(outputPath)) {
      try {
        const raw = fs.readFileSync(outputPath, "utf8");
        regionOrders = JSON.parse(raw);
        console.log(`Loaded ${regionOrders.length} existing records from ${region}.json`);
      } catch (e) {
        console.warn(`Failed to parse existing ${region}.json, starting fresh for this region.`);
      }
    }

    // Isolate current year orders to prevent duplication during merge
    if (IS_DELTA) {
        regionOrders = regionOrders.filter(order => order.year !== CURRENT_YEAR);
    }

    for (let year = END_YEAR; year >= START_YEAR; year--) {
      const targetUrl = `https://www.adfg.alaska.gov/sf/EONR/index.cfm?ADFG=region.${region}&Year=${year}`;
      
      try {
        const response = await fetch(targetUrl);
        const html = await response.text();
        const $ = cheerio.load(html);
        
        let yearCount = 0;

        $("table tr").each((index, element) => {
          if (index === 0 && $(element).find("th").length > 0) return;
          
          const columns = $(element).find("td");
          if (columns.length >= 3) {
            const dateCell = $(columns[0]).text().replace(/\s+/g, " ").trim();
            const area = $(columns[1]).text().trim();
            const summaryLink = $(columns[2]).find("a");
            
            const title = summaryLink.text().replace(/\s+/g, " ").trim();
            let url = summaryLink.attr("href") || "";
            
            if (url && !url.startsWith("http")) {
              url = `https://www.adfg.alaska.gov/sf/EONR/${url}`;
            }

            if (title && url) {
              regionOrders.push({
                year,
                date: dateCell,
                area,
                title,
                url
              });
              yearCount++;
            }
          }
        });
        
        process.stdout.write(`✅ Y: ${year} (${yearCount} records) `);
        
      } catch (err) {
        console.error(`\n❌ Failed to scrape ${region} - ${year}:`, err);
      }

      await sleep(DELAY_MS);
    } // End Years Loop

    // Sort descending by Year -> Date implicitly
    regionOrders.sort((a, b) => b.year - a.year);

    fs.writeFileSync(outputPath, JSON.stringify(regionOrders, null, 2), "utf8");
    console.log(`\n💾 Saved ${regionOrders.length} total records to: /data/${region}.json\n`);
    
  } // End Regions Loop

  console.log(`🎉 Scrape complete. Worker finished successfully.`);
}

scrapeHistoricEmergencyOrders();
