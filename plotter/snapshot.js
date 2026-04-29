#!/usr/bin/env node
/**
 * snapshot.js — headless chart screenshot using QuantJuice snapshot_template.html
 * Usage: node snapshot.js --data <json-file> --output <png-path> [--ticker MSFT] [--width 1400] [--height 900]
 */
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const os = require('os');

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length - 1; i++) {
    if (argv[i].startsWith('--')) args[argv[i].slice(2)] = argv[i + 1];
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.data || !args.output) {
    process.stderr.write('Usage: node snapshot.js --data <json> --output <png> [--ticker X] [--width 1400] [--height 900]\n');
    process.exit(1);
  }

  const chartData = JSON.parse(fs.readFileSync(args.data, 'utf8'));
  const ticker    = args.ticker  || '';
  const width     = parseInt(args.width  || '1400');
  const height    = parseInt(args.height || '900');

  const templatePath = path.join(__dirname, 'snapshot_template.html');
  let html = fs.readFileSync(templatePath, 'utf8');

  // Inject data inline before </head> so it's available before any script runs
  const injection = `<script>
window.__CHART_DATA__ = ${JSON.stringify(chartData)};
window.__TICKER__     = ${JSON.stringify(ticker)};
</script>`;
  html = html.replace('</head>', injection + '\n</head>');

  // Write temp file so file:// URL loads CDN resources properly
  const tmpHtml = path.join(os.tmpdir(), `qj_snap_${Date.now()}_${process.pid}.html`);
  fs.writeFileSync(tmpHtml, html, 'utf8');

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    headless: true,
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({width, height, deviceScaleFactor: 1});
    await page.goto(`file://${tmpHtml}`, {waitUntil: 'networkidle0', timeout: 25000});
    await page.waitForFunction(() => window.__CHART_READY__ === true, {timeout: 15000});
    await new Promise(r => setTimeout(r, 300));
    await page.screenshot({path: args.output, fullPage: false});
    process.stdout.write(args.output + '\n');
  } finally {
    await browser.close();
    try { fs.unlinkSync(tmpHtml); } catch (_) {}
  }
}

main().catch(e => {
  process.stderr.write(e.stack || e.message);
  process.exit(1);
});
