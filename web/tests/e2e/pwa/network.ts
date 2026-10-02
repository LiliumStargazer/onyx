import { createServer, request } from "node:http";
import { connect } from "node:net";
import { test as base } from "@playwright/test";

interface PwaNetwork {
  baseURL: string;
  setOffline: (offline: boolean) => void;
}

// WebKit's setOffline blocks navigation before service workers can return a fallback.
// Close real connections instead. All requests still go through the frontend.
export const test = base.extend<{ pwaNetwork: PwaNetwork }>({
  // eslint-disable-next-line no-empty-pattern -- Playwright requires fixture destructuring.
  pwaNetwork: async ({}, use) => {
    let isOffline = false;
    // ponytail: HTTP-only local proxy; use HTTPS transport for remote test servers.
    const frontendURL = process.env.BASE_URL || "http://localhost:3000";
    const server = createServer((incoming, outgoing) => {
      if (isOffline) {
        incoming.socket.destroy();
        return;
      }
      const upstream = request(
        new URL(incoming.url ?? "/", frontendURL),
        { method: incoming.method, headers: incoming.headers },
        (response) => {
          outgoing.writeHead(response.statusCode ?? 502, response.headers);
          response.pipe(outgoing);
        }
      );
      upstream.on("error", () => outgoing.destroy());
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
