import { expect } from "@playwright/test";
import { test } from "@tests/e2e/pwa/network";
import { PwaPage } from "@tests/e2e/pages/PwaPage";
import { ChatPage } from "@tests/e2e/chat/ChatPage";

test(
  "browser can install Wiki Agent Rag",
  { tag: "@pwa" },
  async ({ page }) => {
    await new PwaPage(page).expectInstallable();
  }
);

test(
  "launch opens Assistant and offline never exposes cached content",
  { tag: "@pwa" },
  async ({ page, pwaNetwork }) => {
    const pwa = new PwaPage(page);
    await pwa.launch();
    await new ChatPage(page).inputBar.fill("Simulated private question");
    pwaNetwork.setOffline(true);
    await pwa.detectConnectionLoss();
    await pwa.expectOffline();
    await pwa.retry();
    await pwa.expectOffline();
    await page.reload();
    await pwa.expectOffline();
    await page.goto("/app?chatId=simulated-private-chat");
    await pwa.expectOffline();
    await page.goto("/api/chat/document/simulated-private-document");
    await pwa.expectOffline();
    await page.goto("/app");
    await pwa.expectOffline();
    pwaNetwork.setOffline(false);
    await pwa.retry();
    await pwa.expectOnline();
    const cachedUrls = await page.evaluate(async () => {
      const urls: string[] = [];
      for (const name of await caches.keys()) {
        const cache = await caches.open(name);
        urls.push(
          ...(await cache.keys()).map(
            (request) => new URL(request.url).pathname
          )
        );
      }
      return urls;
    });
    expect(cachedUrls).toEqual(["/offline.html"]);
  }
);

test(
  "replaces Wiki Copilot's worker and removes only its caches",
  { tag: "@pwa" },
  async ({ page, pwaNetwork }) => {
    const pwa = new PwaPage(page);
    await pwa.visitAfterWikiCopilot();
    pwaNetwork.setOffline(true);
    await page.goto("/app");
    await pwa.expectOffline();
  }
);
