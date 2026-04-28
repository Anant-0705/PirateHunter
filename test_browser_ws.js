const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  page.on('websocket', ws => {
    console.log(`WebSocket opened: ${ws.url()}`);
    ws.on('framesent', event => console.log('WS Sent:', event.payload));
    ws.on('framereceived', event => console.log('WS Received:', event.payload));
    ws.on('socketerror', err => console.log('WS Error:', err));
    ws.on('close', () => console.log('WS Closed'));
  });

  page.on('console', msg => console.log(`BROWSER: ${msg.text()}`));

  console.log("Navigating to dashboard...");
  await page.goto('http://localhost:3000');
  
  await page.waitForTimeout(5000);
  await browser.close();
})();
