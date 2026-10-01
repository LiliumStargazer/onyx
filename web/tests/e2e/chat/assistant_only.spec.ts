import { expect, test } from "@playwright/test";
import { ChatPage } from "@tests/e2e/chat/ChatPage";
import {
  buildMockSearchStream,
  resetTurnCounter,
} from "@tests/e2e/utils/chatMock";
import type { MinimalAgent } from "@/lib/agents/types";
import type { User } from "@/lib/types";
import { ChatSessionSharedStatus } from "@/app/app/interfaces";
import type { BackendChatSession } from "@/app/app/interfaces";
import { SIMPLIFIED_CHAT_ENABLED } from "@/lib/constants";

test.skip(!SIMPLIFIED_CHAT_ENABLED, "Simplified chat is disabled");

const SESSION_ID = "00000000-0000-4000-8000-000000000023";
const assistant: MinimalAgent = {
  id: 0,
  name: "Assistant",
  description: "",
  tools: [
    {
      id: 1,
      name: "Search",
      display_name: "Search",
      description: "Search",
      in_code_tool_id: "SearchTool",
      definition: null,
      custom_headers: [],
      passthrough_auth: false,
      enabled: true,
      chat_selectable: true,
      agent_creation_selectable: true,
      default_enabled: true,
    },
  ],
  starter_messages: null,
  document_sets: [],
  is_public: true,
  is_listed: true,
  display_priority: null,
  is_featured: false,
  builtin_persona: true,
  owner: null,
  owner_group: null,
  user_permission: null,
};
const customAgent = {
  ...assistant,
  id: 23,
  name: "Simulated custom agent",
  builtin_persona: false,
};

for (const viewport of [
  { width: 1280, height: 720 },
  { width: 390, height: 844 },
]) {
  test(`Assistant chat rejects attachments and preserves citations at width ${viewport.width}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    resetTurnCounter();
    const chat = new ChatPage(page);
    const uploadRequests: string[] = [];
    const chatRequests: { message: string; file_descriptors: unknown[] }[] = [];
    const createdAgents: number[] = [];
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
      current_alternate_model: undefined,
      current_temperature_override: null,
      current_reasoning_effort_override: null,
      owner_name: null,
    };
    await page.route("**/api/me", async (route) => {
      const response = await route.fetch();
      const user: User = await response.json();
      await route.fulfill({
        response,
        json: {
          ...user,
          personalization: { ...user.personalization, name: "Test User" },
          preferences: {
            ...user.preferences,
            pinned_assistants: [23],
            default_app_mode: "SEARCH",
            voice_auto_playback: false,
          },
        },
      });
    });
    await page.route("**/api/persona", (route) =>
      route.fulfill({ json: [assistant, customAgent] })
    );
    await page.route("**/api/settings", async (route) => {
      const response = await route.fetch();
      await route.fulfill({
        response,
        json: {
          ...(await response.json()),
          tier: "business",
          ee_features_enabled: true,
          search_ui_enabled: true,
          deep_research_enabled: true,
          vector_db_enabled: true,
        },
      });
    });
    await page.route("**/api/manage/connector-status**", (route) =>
      route.fulfill({
        json: [
          {
            id: 1,
            name: "Simulated Wiki",
            source: "wikijs",
            connector: { source: "wikijs", input_type: "poll" },
            access_type: "public",
          },
        ],
      })
    );
    await page.route("**/api/voice/status", (route) =>
      route.fulfill({ json: { stt_enabled: true, tts_enabled: false } })
    );
    const providerResponse = {
      providers: [
        {
          id: 50,
          name: "Test Provider",
          provider: "openai",
          provider_display_name: "Test Provider",
          model_configurations: [
            {
              id: 501,
              name: "admin-model",
              is_visible: true,
              max_input_tokens: 32000,
              supports_image_input: false,
              supports_reasoning: false,
            },
          ],
        },
      ],
      default_text: { provider_id: 50, model_name: "admin-model" },
      default_vision: null,
      default_chat_naming: null,
      default_craft: null,
    };
    for (const endpoint of [
      "**/api/llm/provider",
      "**/api/llm/persona/*/providers",
    ]) {
      await page.route(endpoint, (route) =>
        route.fulfill({ json: providerResponse })
      );
    }
    await page.route("**/api/chat/get-user-chat-sessions**", (route) =>
      route.fulfill({ json: { sessions: [], has_more: false } })
    );
    await page.route("**/api/chat/create-chat-session", (route) => {
      const payload: { persona_id: number } = route.request().postDataJSON();
      createdAgents.push(payload.persona_id);
      return route.fulfill({ json: { chat_session_id: SESSION_ID } });
    });
    await page.route(`**/api/chat/get-chat-session/${SESSION_ID}`, (route) =>
      route.fulfill({ json: session })
    );
    await page.route("**/api/chat/update-chat-session-*", (route) =>
      route.fulfill({ json: {} })
    );
    await page.route("**/api/chat/rename-chat-session", (route) =>
      route.fulfill({ json: {} })
    );
    await page.route("**/api/user/projects/file/upload", (route) => {
      uploadRequests.push(route.request().url());
      return route.fulfill({
        status: 400,
        json: { detail: "Unexpected chat upload" },
      });
    });
    await page.route("**/api/chat/send-chat-message", (route) => {
      chatRequests.push(route.request().postDataJSON());
      return route.fulfill({
        contentType: "text/plain",
        body: buildMockSearchStream({
          content: "Simulated answer [[D1]](https://example.com/wiki)",
          queries: ["Simulated question"],
          documents: [
            {
              document_id: "simulated-wiki-page",
              semantic_identifier: "Simulated Wiki page",
              link: "https://example.com/wiki",
              source_type: "wikijs",
              blurb: "Simulated content",
              is_internet: false,
            },
          ],
          citations: { 1: "simulated-wiki-page" },
          isInternetSearch: false,
        }),
      });
    });

    await chat.goto();
    await chat.expectAssistantOnly();
    await chat.inputBar.pasteFile();
    await chat.inputBar.dropFile();
    await chat.inputBar.expectEmpty();
    await chat.inputBar.paste("Simulated question");
    await chat.inputBar.expectText("Simulated question");
    await chat.inputBar.send();
    await chat.expectHumanMessage("Simulated question");
    await expect(chat.aiMessage()).toContainText("Simulated answer");
    expect(createdAgents).toEqual([0]);
    expect(chatRequests).toHaveLength(1);
    expect(chatRequests[0]?.file_descriptors).toEqual([]);
    expect(uploadRequests).toEqual([]);
    await chat.expectAssistantOnly();
    await chat.expectCitedSources();
    await chat.inputBar.fill("Second question");
    await chat.inputBar.send();
    await chat.expectHumanMessage("Second question", 1);
    await expect(chat.aiMessage(1)).toContainText("Simulated answer");
    expect(chatRequests).toHaveLength(2);

    if (viewport.width === 1280) {
      await chat.openChatHistorySearch();
      const customSessionId = "00000000-0000-4000-8000-000000000123";
      await page.route(
        `**/api/chat/get-chat-session/${customSessionId}`,
        (route) =>
          route.fulfill({
            json: {
              ...session,
              chat_session_id: customSessionId,
              persona_id: 23,
              persona_name: customAgent.name,
            },
          })
      );
      for (const path of [
        "/admin/agents",
        "/ee/agents/stats/23",
        "/app?agentId=23",
        "/app/agents",
        "/app/agents/create",
        "/app/agents/edit/23",
        `/app?chatId=${customSessionId}`,
      ]) {
        await chat.gotoAgentUrl(path);
        await chat.expectAssistantOnly();
      }
      await chat.expectAdminAgentsHidden();

      for (const personaId of [23, 0]) {
        const delayedSessionId =
          personaId === 0
            ? "00000000-0000-4000-8000-000000000024"
            : "00000000-0000-4000-8000-000000000025";
        const sessionRequested = Promise.withResolvers<void>();
        const releaseSession = Promise.withResolvers<void>();
        await page.route(
          `**/api/chat/get-chat-session/${delayedSessionId}`,
          async (route) => {
            sessionRequested.resolve();
            await releaseSession.promise;
            await route.fulfill({
              json: {
                ...session,
                chat_session_id: delayedSessionId,
                persona_id: personaId,
                persona_name:
                  personaId === 0 ? assistant.name : customAgent.name,
              },
            });
          }
        );
        await chat.gotoSessionPrompt(delayedSessionId, "Delayed question");
        await sessionRequested.promise;
        await chat.inputBar.expectDisabled();
        expect(chatRequests).toHaveLength(2);
        releaseSession.resolve();
        if (personaId !== 0) {
          await chat.expectAssistantRedirect();
          expect(chatRequests).toHaveLength(2);
        } else {
          await chat.expectHumanMessage("Delayed question");
          await expect(chat.aiMessage()).toContainText("Simulated answer");
          expect(chatRequests).toHaveLength(3);
          await chat.inputBar.fill("Follow-up question");
          await chat.inputBar.send();
          await chat.expectHumanMessage("Follow-up question", 1);
          expect(chatRequests).toHaveLength(4);
        }
      }
    }
  });
}
