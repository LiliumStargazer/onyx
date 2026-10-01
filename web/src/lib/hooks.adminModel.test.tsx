import type { ReactNode } from "react";
import { SWRConfig } from "swr";
import {
  act,
  renderHook,
  waitFor,
  makeProvider,
} from "@tests/setup/test-utils";
import { useLlmManager } from "@/lib/hooks";
import { ChatSession, ChatSessionSharedStatus } from "@/app/app/interfaces";
import type { MinimalAgent } from "@/lib/agents/types";
import type {
  LLMProviderDescriptor,
  LLMProviderResponse,
} from "@/lib/languageModels/types";

jest.mock("next/navigation", () => ({ usePathname: () => "/app" }));

const assistant: MinimalAgent = {
  id: 0,
  name: "Assistant",
  description: "",
  tools: [],
  starter_messages: null,
  document_sets: [],
  default_model_configuration_id: 502,
  is_public: true,
  is_listed: true,
  display_priority: 0,
  is_featured: false,
  builtin_persona: true,
  owner: null,
  owner_group: null,
  user_permission: null,
};
const providerResponse: LLMProviderResponse<LLMProviderDescriptor> = {
  providers: [
    makeProvider({
      id: 50,
      name: "Test Provider",
      model_configurations: ["saved-model", "admin-model"].map(
        (name, index) => ({
          id: 502 - index,
          name,
          effectiveDisplayName: name,
          is_visible: true,
          max_input_tokens: 32000,
          supports_image_input: false,
          supports_reasoning: false,
        })
      ),
    }),
  ],
  default_text: { provider_id: 50, model_name: "admin-model" },
  default_vision: null,
  default_chat_naming: null,
  default_craft: null,
};
const adminModel = {
  name: "Test Provider",
  provider: "openai",
  modelName: "admin-model",
  modelConfigurationId: 501,
};

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), shouldRetryOnError: false }}>
      {children}
    </SWRConfig>
  );
}

let failGlobalRequest = false;
let fetchSpy: jest.SpiedFunction<typeof fetch>;
beforeEach(() => {
  failGlobalRequest = false;
  fetchSpy = jest.spyOn(global, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    // GET /api/llm/provider supplies the global Admin default.
    if (url === "/api/llm/provider") {
      return new Response(
        JSON.stringify(
          failGlobalRequest ? { detail: "Temporary error" } : providerResponse
        ),
        { status: failGlobalRequest ? 500 : 200 }
      );
    }
    // GET /api/llm/persona/0/providers supplies a different agent default.
    if (url === "/api/llm/persona/0/providers") {
      return new Response(
        JSON.stringify({
          ...providerResponse,
          default_text: { provider_id: 50, model_name: "saved-model" },
        })
      );
    }
    throw new Error(`Unexpected request: ${url}`);
  });
});
afterEach(() => fetchSpy.mockRestore());

test("the Admin model overrides saved chat choices, agent defaults, and manual choices", async () => {
  const session: ChatSession = {
    id: "session-1",
    name: "",
    persona_id: 0,
    time_created: "",
    time_updated: "",
    shared_status: ChatSessionSharedStatus.Private,
    project_id: null,
    current_alternate_model: "Test Provider__openai__saved-model__mc:502",
    current_temperature_override: null,
    current_reasoning_effort_override: null,
  };
  const { result, rerender } = renderHook(
    (props: { session?: ChatSession }) =>
      useLlmManager(props.session, assistant),
    { initialProps: {}, wrapper: Wrapper }
  );
  await waitFor(() => expect(result.current.isLoadingProviders).toBe(false));
  expect(result.current.currentLlm).toEqual(adminModel);
  rerender({ session });
  expect(result.current.currentLlm).toEqual(adminModel);
  act(() =>
    result.current.updateCurrentLlm({
      ...adminModel,
      modelName: "saved-model",
      modelConfigurationId: 502,
    })
  );
  expect(result.current.currentLlm).toEqual(adminModel);
});

test("a failed global model request stays unselected until a successful retry", async () => {
  failGlobalRequest = true;
  const { result } = renderHook(() => useLlmManager(undefined, assistant), {
    wrapper: Wrapper,
  });
  await waitFor(() => expect(result.current.isLoadingProviders).toBe(false));
  expect(result.current.currentLlm.modelName).toBe("");
  failGlobalRequest = false;
  await act(async () => {
    await result.current.refetchProviders();
  });
  expect(result.current.currentLlm).toEqual(adminModel);
});
