import { expect, test } from "@playwright/test";
import { ChatPage } from "@tests/e2e/chat/ChatPage";
import { SettingsChatsPage } from "@tests/e2e/pages/SettingsChatsPage";
import type { User } from "@/lib/types";
import { buildMockStream, resetTurnCounter } from "@tests/e2e/utils/chatMock";
import { ChatSessionSharedStatus, toChatSession } from "@/app/app/interfaces";
import type { BackendChatSession } from "@/app/app/interfaces";
import type { LLMOverride } from "@/app/app/services/lib";

const SESSION_ID = "00000000-0000-4000-8000-000000000022";
const SAVED_MODEL = "Test Provider__openai__saved-model__mc:502";
const ADMIN_MODEL = {
  model_provider: "Test Provider",
  model_version: "admin-model",
  model_configuration_id: 501,
};

for (const scenario of ["new", "existing", "retry"] as const) {
  test(`${scenario} chat and regeneration use the Admin model despite saved choices`, async ({
    page,
  }) => {
    const existingChat = scenario === "existing";
    let failProviderRequest = scenario === "retry";
    resetTurnCounter();
    const chat = new ChatPage(page);
    const capturedOverrides: (LLMOverride | undefined)[] = [];
    const session: BackendChatSession = {
      chat_session_id: SESSION_ID,
      description: "Simulated chat",
      persona_id: 0,
      persona_name: "Assistant",
      messages: [],
      packets: [],
      time_created: "2026-01-01T00:00:00Z",
      time_updated: "2026-01-01T00:00:00Z",
      shared_status: ChatSessionSharedStatus.Private,
      current_alternate_model: SAVED_MODEL,
      current_temperature_override: null,
      current_reasoning_effort_override: null,
      owner_name: null,
    };

    // Mock model configuration and saved preferences, not the chat implementation.
    await page.route("**/api/me", async (route) => {
      const response = await route.fetch();
      const user: User = await response.json();
      await route.fulfill({
        response,
        json: {
          ...user,
          preferences: { ...user.preferences, default_model: SAVED_MODEL },
        },
      });
    });
    const providerResponse = {
      providers: [
        {
          id: 50,
          name: "Test Provider",
          provider: "openai",
          provider_display_name: "Test Provider",
          model_configurations: ["admin-model", "saved-model"].map(
            (name, index) => ({
              id: 501 + index,
              name,
              is_visible: true,
              max_input_tokens: 32000,
              supports_image_input: false,
              supports_reasoning: false,
            })
          ),
        },
      ],
      default_text: { provider_id: 50, model_name: "admin-model" },
      default_vision: null,
      default_chat_naming: null,
      default_craft: null,
    };
    await page.route("**/api/llm/provider", (route) =>
      route.fulfill({
        status: failProviderRequest ? 500 : 200,
        json: failProviderRequest
          ? { detail: "Temporary provider error" }
          : providerResponse,
      })
    );
    await page.route("**/api/llm/persona/*/providers", (route) =>
      route.fulfill({
        json: {
          ...providerResponse,
          default_text: { provider_id: 50, model_name: "saved-model" },
        },
      })
    );
    await page.route("**/api/chat/get-user-chat-sessions**", (route) =>
      route.fulfill({
        json: {
          sessions: existingChat ? [toChatSession(session)] : [],
          has_more: false,
        },
      })
    );
    await page.route("**/api/chat/create-chat-session", (route) =>
      route.fulfill({ json: { chat_session_id: SESSION_ID } })
    );
    await page.route(`**/api/chat/get-chat-session/${SESSION_ID}`, (route) =>
      route.fulfill({ json: session })
    );
    await page.route("**/api/chat/update-chat-session-*", (route) =>
      route.fulfill({ json: {} })
    );
    await page.route("**/api/chat/rename-chat-session", (route) =>
      route.fulfill({ json: {} })
    );
    await page.route("**/api/chat/send-chat-message", async (route) => {
      const payload: {
        llm_override?: LLMOverride;
        llm_overrides?: LLMOverride[] | null;
      } = route.request().postDataJSON();
      capturedOverrides.push(payload.llm_override);
      expect(payload.llm_overrides).toBeNull();
      await route.fulfill({
        contentType: "text/plain",
        body: buildMockStream("Simulated Admin response"),
      });
    });

    await chat.goto(existingChat ? SESSION_ID : undefined);
    if (failProviderRequest) {
      await chat.expectModelLoadError();
      expect(capturedOverrides).toHaveLength(0);
      failProviderRequest = false;
      await chat.retryModelLoad();
    }
    await chat.expectNoModelSelectors();
    await chat.inputBar.fill("Use the Admin model");
    await chat.inputBar.send();
    await expect.poll(() => capturedOverrides.length).toBe(1);
    expect(capturedOverrides[0]).toMatchObject(ADMIN_MODEL);
    await expect(chat.aiMessage()).toContainText("Simulated Admin response");
    await chat.expectNoModelSelectors();

    await chat.regenerate();
    await expect.poll(() => capturedOverrides.length).toBe(2);
    expect(capturedOverrides[1]).toMatchObject(ADMIN_MODEL);

    const settings = new SettingsChatsPage(page);
    await settings.goto();
    await settings.expectNoModelSelector();
  });
}
