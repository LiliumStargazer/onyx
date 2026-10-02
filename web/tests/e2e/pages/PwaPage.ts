import { expect, type Page } from "@playwright/test";
import type { MetadataRoute } from "next";
import { ChatPage } from "@tests/e2e/chat/ChatPage";

export class PwaPage {
  constructor(readonly page: Page) {}

  async expectInstallable(): Promise<void> {
    await this.page.goto("/auth/error");
    await expect(this.page.locator('link[rel="manifest"]')).toHaveAttribute(
      "href",
      "/manifest.webmanifest"
    );
    await expect(
      this.page.locator('link[rel="apple-touch-icon"]')
    ).toHaveAttribute("href", "/pwa/icon-180.png");
    const response = await this.page.request.get("/manifest.webmanifest");
    expect(response.ok()).toBe(true);
    const manifest: MetadataRoute.Manifest = await response.json();
    expect(manifest).toMatchObject({
      name: "Wiki Agent Rag",
      short_name: "Wiki Agent Rag",
      start_url: "/app",
      scope: "/",
      display: "standalone",
      icons: [
        { src: "/wiki-agent-rag.png", sizes: "192x192", type: "image/png" },
        { src: "/pwa/icon-512.png", sizes: "512x512", type: "image/png" },
      ],
    });
    for (const icon of manifest.icons ?? []) {
      const iconResponse = await this.page.request.get(icon.src);
      expect(iconResponse.ok()).toBe(true);
      expect(iconResponse.headers()["content-type"]).toContain("image/png");
    }
    await this.waitForWorker();
    if (this.page.context().browser()?.browserType().name() === "chromium") {
      const session = await this.page.context().newCDPSession(this.page);
      await expect
        .poll(
          async () =>
            (await session.send("Page.getInstallabilityErrors"))
              .installabilityErrors
        )
        .toEqual([]);
      await session.detach();
    }
  }

  async visitAfterWikiCopilot(): Promise<void> {
    // Simulate Wiki Copilot's root worker and cached documents on this origin.
    await this.page.context().route("**/sw.js?legacy=1", (route) =>
      route.fulfill({
        contentType: "application/javascript",
        body: `
          self.addEventListener('install', () => self.skipWaiting());
          self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
          self.addEventListener('fetch', event => {
            event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
          });
        `,
      })
    );
    await this.page.goto("/offline.html");
    await this.page.evaluate(async () => {
      const cache = await caches.open("wikicopilot-v1");
      await cache.put("/app", new Response("Simulated cached private answer"));
      await cache.put(
        "/api/chat/document/simulated",
        new Response("Simulated cached private document")
      );
      await caches.open("unrelated-app");
      await navigator.serviceWorker.register("/sw.js?legacy=1");
      await navigator.serviceWorker.ready;
    });
    await expect
      .poll(() =>
        this.page.evaluate(() => navigator.serviceWorker.controller?.scriptURL)
      )
      .toMatch(/\/sw\.js\?legacy=1$/);
    await this.launch();
    await expect
      .poll(() => this.page.evaluate(async () => (await caches.keys()).sort()))
      .toEqual(["unrelated-app", "wiki-agent-rag-offline-v1"]);
  }

  async waitForWorker(): Promise<void> {
    await this.page.evaluate(async () => {
      await navigator.serviceWorker.ready;
    });
    await expect
      .poll(() =>
        this.page.evaluate(() => navigator.serviceWorker.controller?.scriptURL)
      )
      .toMatch(/\/sw\.js$/);
  }

  async launch(): Promise<void> {
    const response = await this.page.request.get("/manifest.webmanifest");
    const manifest: MetadataRoute.Manifest = await response.json();
    if (!manifest.start_url) throw new Error("Missing PWA start URL");
    await this.page.goto(manifest.start_url);
    await new ChatPage(this.page).inputBar.textbox.waitFor({
      state: "visible",
    });
    await expect(this.page).toHaveURL(/\/app$/);
    await expect(this.page.locator("#onyx-human-message")).toHaveCount(0);
    await expect(this.page.getByTestId("agent-name-display")).toHaveCount(0);
    await this.waitForWorker();
  }

  async expectOnline(): Promise<void> {
    await expect(new ChatPage(this.page).inputBar.textbox).toBeVisible();
    await expect(this.page).toHaveURL(/\/app$/);
  }

  async detectConnectionLoss(): Promise<void> {
    await this.page.evaluate(() => {
      // A request fails even when Wi-Fi stays connected but the Internet is unavailable.
      void fetch("/api/health").catch(() => {});
    });
  }

  async expectOffline(): Promise<void> {
    await expect(
      this.page.getByRole("heading", { name: "Connessione assente" })
    ).toBeVisible();
    await expect(
      this.page.getByRole("button", { name: "Riprova", exact: true })
    ).toBeVisible();
    await expect(this.page.locator("body")).toHaveText(
      "Connessione assente Riprova"
    );
    await expect(this.page.getByRole("textbox")).toHaveCount(0);
  }

  async retry(): Promise<void> {
    await this.page
      .getByRole("button", { name: "Riprova", exact: true })
      .click();
  }
}
