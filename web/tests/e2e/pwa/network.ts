import { createServer, request } from "node:http";
import { connect } from "node:net";
import { expect, test as base, type Page } from "@playwright/test";
import { PwaPage } from "@tests/e2e/pages/PwaPage";

interface PwaNetwork {
  baseURL: string;
  setOffline: (offline: boolean) => void;
  holdChatResponse: () => void;
}

// WebKit's setOffline blocks navigation before service workers can return a fallback.
// Close real connections instead. All requests still go through the frontend.
export const test = base.extend<{ pwaNetwork: PwaNetwork }>({
  // eslint-disable-next-line no-empty-pattern -- Playwright requires fixture destructuring.
  pwaNetwork: async ({}, use) => {
    let isOffline = false;
    let shouldHoldChatResponse = false;
    // ponytail: HTTP-only local proxy; use HTTPS transport for remote test servers.
    const frontendURL = process.env.BASE_URL || "http://localhost:3000";
    const server = createServer((incoming, outgoing) => {
      incoming.on("error", () => outgoing.destroy());
      if (isOffline) {
        incoming.socket.destroy();
        return;
      }
      // Keep PWA checks independent of real models and private documents.
      if (incoming.url === "/api/chat/send-chat-message") {
        outgoing.writeHead(200, { "Content-Type": "application/json" });
        for (const packet of [
          { user_message_id: 1, reserved_assistant_message_id: 2 },
          {
            placement: { turn_index: 0 },
            obj: {
              type: "message_start",
              id: "simulated",
              final_documents: [],
            },
          },
          {
            placement: { turn_index: 0 },
            obj: { type: "message_delta", content: "Simulated private answer" },
          },
        ]) {
          outgoing.write(`${JSON.stringify(packet)}\n`);
        }
        if (!shouldHoldChatResponse) {
          outgoing.end(
            `${JSON.stringify({
              placement: { turn_index: 0 },
              obj: { type: "stop", stop_reason: "finished" },
            })}\n`
          );
        }
        incoming.resume();
        return;
      }
      const upstream = request(
        new URL(incoming.url ?? "/", frontendURL),
        { method: incoming.method, headers: incoming.headers },
        (response) => {
          outgoing.writeHead(response.statusCode ?? 502, response.headers);
          response.on("error", () => outgoing.destroy());
          response.pipe(outgoing);
        }
      );
      upstream.on("error", () => outgoing.destroy());
      outgoing.on("close", () => upstream.destroy());
      incoming.pipe(upstream);
    });
    // Preserve Next.js's development WebSocket so hydration can finish.
    server.on("upgrade", (incoming, socket, head) => {
      const frontend = new URL(frontendURL);
      const upstream = connect(
        Number(frontend.port || 80),
        frontend.hostname,
        () => {
          upstream.write(`${incoming.method} ${incoming.url} HTTP/1.1\r\n`);
          for (let index = 0; index < incoming.rawHeaders.length; index += 2) {
            upstream.write(
              `${incoming.rawHeaders[index]}: ${incoming.rawHeaders[index + 1]}\r\n`
            );
          }
          upstream.write("\r\n");
          upstream.write(head);
          socket.pipe(upstream).pipe(socket);
        }
      );
      upstream.on("error", () => socket.destroy());
      socket.on("error", () => upstream.destroy());
      socket.on("close", () => upstream.destroy());
    });
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve)
    );
    const address = server.address();
    if (!address || typeof address === "string")
      throw new Error("Missing proxy port");
    try {
      await use({
        baseURL: `http://localhost:${address.port}`,
        setOffline: (offline) => {
          isOffline = offline;
          if (offline) server.closeAllConnections();
        },
        holdChatResponse: () => {
          shouldHoldChatResponse = true;
        },
      });
    } finally {
      server.closeAllConnections();
      await new Promise<void>((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve()))
      );
    }
  },
  baseURL: async ({ pwaNetwork }, use) => use(pwaNetwork.baseURL),
});

export async function prepareWikiCopilotLegacy(page: Page): Promise<void> {
  // Simulate Wiki Copilot legacy's root worker and cached documents on this origin.
  await page.context().route("**/sw.js?legacy=1", (route) =>
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
  await new PwaPage(page).visit("/offline.html");
  await page.evaluate(async () => {
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
      page.evaluate(() => navigator.serviceWorker.controller?.scriptURL)
    )
    .toMatch(/\/sw\.js\?legacy=1$/);
}
