import { expect } from "@playwright/test";
import { prepareWikiCopilotLegacy, test } from "@tests/e2e/pwa/network";
import { PwaPage } from "@tests/e2e/pages/PwaPage";
import { ChatPage } from "@tests/e2e/chat/ChatPage";

test("browser can install Wiki Copilot", { tag: "@pwa" }, async ({ page }) => {
  await new PwaPage(page).expectInstallable();
});

test(
  "launch opens Assistant and offline never exposes cached content",
  { tag: "@pwa" },
  async ({ page, pwaNetwork }) => {
    const pwa = new PwaPage(page);
    const chat = new ChatPage(page);
    await pwa.launch();
    await chat.inputBar.fill("Simulated private question");
    await chat.inputBar.clickSend();
    await expect(chat.aiMessage()).toContainText("Simulated private answer");
    pwaNetwork.setOffline(true);
    await pwa.expectOffline();
    await pwa.retry();
    await pwa.expectOffline();
    await pwa.reload();
    await pwa.expectOffline();
    await pwa.visit("/app?chatId=simulated-private-chat");
    await pwa.expectOffline();
    await pwa.visit("/api/chat/document/simulated-private-document");
    await pwa.expectOffline();
    await pwa.visit("/app");
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
  "a streaming answer disappears when Wi-Fi loses its uplink",
  { tag: "@pwa" },
  async ({ page, pwaNetwork }) => {
    const pwa = new PwaPage(page);
    const chat = new ChatPage(page);
    await pwa.launch();
    pwaNetwork.holdChatResponse();
    await chat.inputBar.fill("Simulated private question");
    await chat.inputBar.clickSend();
    await chat.expectAnswer("Simulated private answer");
    pwaNetwork.setOffline(true);
    await pwa.expectOffline();
  }
);

test(
  "replaces Wiki Copilot legacy's worker and removes only its caches",
  { tag: "@pwa" },
  async ({ page, pwaNetwork }) => {
    const pwa = new PwaPage(page);
    await prepareWikiCopilotLegacy(page);
    await pwa.launch();
    await expect
      .poll(() => page.evaluate(async () => (await caches.keys()).sort()))
      .toEqual(["unrelated-app", "wiki-copilot-offline-v1"]);
    pwaNetwork.setOffline(true);
    await pwa.expectOffline();
    await pwa.visit("/app");
    await pwa.expectOffline();
  }
);
