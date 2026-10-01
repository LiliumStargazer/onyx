import { expect, test } from "@playwright/test";
import { ChatPage } from "@tests/e2e/chat/ChatPage";
import { loginAsWorkerUser } from "@tests/e2e/utils/auth";
import { OnyxApiClient } from "@tests/e2e/utils/onyxApiClient";
import type { BackendChatSession } from "@/app/app/interfaces";

let personaId: number;
test.beforeAll(async ({ request }) => {
  // No connector search or embeddings are needed for this ordinary chat.
  personaId = await new OnyxApiClient(request).createAgent(
    "Simulated chat agent"
  );
});
test.afterAll(async ({ request }) => {
  await new OnyxApiClient(request).deleteAgent(personaId);
});

for (const role of ["admin", "user"] as const) {
  test(`Projects APIs deny ${role} access through the frontend`, async ({
    page,
  }, testInfo) => {
    if (role === "user") await loginAsWorkerUser(page, testInfo.workerIndex);
    const sessionId = "00000000-0000-4000-8000-000000000024";
    const fileId = "00000000-0000-4000-8000-000000000025";
    const routes: [string, string][] = [
      ["GET", ""],
      ["POST", "/create?name=Simulated%20Project"],
      ["GET", "/24"],
      ["GET", "/files/24"],
      ["GET", "/24/details"],
      ["GET", "/24/instructions"],
      ["POST", "/24/instructions?instructions=Simulated"],
      ["PATCH", "/24?name=Simulated"],
      ["DELETE", "/24"],
      ["POST", `/24/files/${fileId}`],
      ["DELETE", `/24/files/${fileId}`],
      ["GET", "/24/token-count"],
      ["POST", "/24/move_chat_session"],
      ["POST", "/remove_chat_session"],
    ];
    for (const [method, path] of routes) {
      const response = await page.request.fetch(`/api/user/projects${path}`, {
        method,
        data: { chat_session_id: sessionId },
      });
      expect(response.status(), `${method} ${path}`).toBe(403);
    }
    const upload = await page.request.post("/api/user/projects/file/upload", {
      multipart: {
        project_id: "24",
        files: {
          name: "simulated.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("Simulated"),
        },
      },
    });
    expect(upload.status()).toBe(403);
    for (const projectId of [0, 24]) {
      const create = await page.request.post("/api/chat/create-chat-session", {
        data: { project_id: projectId },
      });
      expect(create.status()).toBe(403);
      const history = await page.request.get(
        `/api/chat/get-user-chat-sessions?project_id=${projectId}`
      );
      expect(history.status()).toBe(403);
      for (const stream of [true, false]) {
        const send = await page.request.post("/api/chat/send-chat-message", {
          data: {
            message: "Simulated",
            chat_session_info: { project_id: projectId },
            stream,
          },
        });
        expect(send.status()).toBe(403);
      }
    }
    // File APIs remain available independently of Projects.
    const statuses = await page.request.post(
      "/api/user/projects/file/statuses",
      {
        data: { file_ids: [] },
      }
    );
    expect(statuses.status()).toBe(200);
    expect(await statuses.json()).toEqual([]);
    for (const suffix of ["files", "token-count"]) {
      const missing = await page.request.get(
        `/api/user/projects/session/${sessionId}/${suffix}`
      );
      expect(missing.status()).toBe(404);
    }
    const create = await page.request.post("/api/chat/create-chat-session", {
      data: {
        description: "Ordinary simulated chat",
        project_id: null,
        persona_id: personaId,
      },
    });
    expect(create.status()).toBe(200);
    const session: { chat_session_id: string } = await create.json();
    try {
      const read = await page.request.get(
        `/api/chat/get-chat-session/${session.chat_session_id}`
      );
      expect(read.status()).toBe(200);
      const send = await page.request.post("/api/chat/send-chat-message", {
        data: {
          message: "Hello",
          chat_session_id: session.chat_session_id,
          allowed_tool_ids: [],
          mock_llm_response: "Simulated ordinary answer",
          stream: false,
        },
      });
      expect(send.status()).toBe(200);
      const answer: { answer: string; error_msg: string | null } =
        await send.json();
      expect(answer.error_msg).toBeNull();
      expect(answer.answer).toBe("Simulated ordinary answer");
    } finally {
      await page.request.delete(
        `/api/chat/delete-chat-session/${session.chat_session_id}`
      );
    }
  });

  test(`Projects navigation and direct URLs are unavailable for ${role}`, async ({
    page,
  }, testInfo) => {
    if (role === "user") await loginAsWorkerUser(page, testInfo.workerIndex);
    const chat = new ChatPage(page);
    await chat.gotoProjectUrl("/app?projectId=24");
    await chat.expectProjectsUnavailable();
    const create = await page.request.post("/api/chat/create-chat-session", {
      data: { description: "Ordinary browser chat", persona_id: personaId },
    });
    expect(create.status()).toBe(200);
    const session: { chat_session_id: string } = await create.json();
    try {
      const send = await page.request.post("/api/chat/send-chat-message", {
        data: {
          message: "Hello",
          chat_session_id: session.chat_session_id,
          mock_llm_response: "Simulated ordinary answer",
          stream: false,
        },
      });
      expect(send.status()).toBe(200);
      // The browser presents Assistant; the API test agent needs no search index.
      await page.route(
        `**/api/chat/get-chat-session/${session.chat_session_id}*`,
        async (route) => {
          const response = await route.fetch();
          const savedChat: BackendChatSession = await response.json();
          await route.fulfill({
            response,
            json: { ...savedChat, persona_id: 0, persona_name: "Assistant" },
          });
        }
      );
      await chat.goto(session.chat_session_id);
      await chat.expectHumanMessage("Hello");
      await expect(chat.aiMessage()).toContainText("Simulated ordinary answer");
      await chat.expectNoProjectChatActions();
    } finally {
      await page.request.delete(
        `/api/chat/delete-chat-session/${session.chat_session_id}`
      );
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await chat.gotoProjectUrl("/app?projectId=24&personaId=24");
    await chat.expectProjectsUnavailable();
  });
}
