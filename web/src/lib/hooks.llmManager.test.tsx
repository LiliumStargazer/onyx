import { act, renderHook } from "@tests/setup/test-utils";
import { useLlmManager } from "@/lib/hooks";
import { ChatSession, ChatSessionSharedStatus } from "@/app/app/interfaces";
import {
  DefaultModel,
  LLMProviderDescriptor,
  ReasoningEffortOverride,
} from "@/lib/languageModels/types";

import {
  updateReasoningEffortForChatSession,
  updateTemperatureOverrideForChatSession,
} from "@/app/app/services/lib";

let mockProviders: LLMProviderDescriptor[] = [];
let mockDefaultText: DefaultModel | null = null;

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: {
      preferences: {
        default_model: "Test Provider__openai__saved-model__mc:502",
      },
    },
  }),
}));
jest.mock("@/lib/languageModels/hooks", () => {
  const getModelResponse = () => ({
    llmProviders: mockProviders,
    defaultText: mockDefaultText,
    isLoading: false,
  });
  return {
    useLanguageModels: getModelResponse,
    useLanguageModelsForAgent: () => ({
      ...getModelResponse(),
      defaultText: mockDefaultText
        ? { provider_id: 50, model_name: "saved-model" }
        : null,
    }),
  };
});
jest.mock("@/app/app/services/lib", () => ({
  updateReasoningEffortForChatSession: jest.fn(),
  updateTemperatureOverrideForChatSession: jest.fn(),
}));

function makeSession(
  id: string,
  reasoningEffort: ReasoningEffortOverride | null
): ChatSession {
  return {
    id,
    name: "",
    persona_id: 0,
    time_created: "",
    time_updated: "",
    shared_status: ChatSessionSharedStatus.Private,
    project_id: null,
    current_alternate_model: "",
    current_temperature_override: null,
    current_reasoning_effort_override: reasoningEffort,
  };
}

interface HookProps {
  session?: ChatSession;
}

describe("useLlmManager override persistence", () => {
  beforeEach(() => {
    mockProviders = [];
    mockDefaultText = null;
    const ok = { ok: true, status: 200 } as Response;
    jest.mocked(updateReasoningEffortForChatSession).mockResolvedValue(ok);
    jest.mocked(updateTemperatureOverrideForChatSession).mockResolvedValue(ok);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test("the Admin model overrides saved preferences, chat choices, and manual choices", () => {
    mockProviders = [
      {
        id: 50,
        name: "Test Provider",
        provider: "openai",
        provider_display_name: "Test Provider",
        model_configurations: ["admin-model", "saved-model"].map(
          (name, index) => ({
            id: 501 + index,
            name,
            effectiveDisplayName: name,
            is_visible: true,
            max_input_tokens: 32000,
            supports_image_input: false,
            supports_reasoning: false,
          })
        ),
      },
    ];
    mockDefaultText = { provider_id: 50, model_name: "admin-model" };
    const session = {
      ...makeSession("session-1", null),
      current_alternate_model: "Test Provider__openai__saved-model__mc:502",
    };
    const { result, rerender } = renderHook(
      (props: HookProps) => useLlmManager(props.session),
      { initialProps: {} }
    );
    const adminModel = {
      name: "Test Provider",
      provider: "openai",
      modelName: "admin-model",
      modelConfigurationId: 501,
    };
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

  test("a persistOverrides reference taken before the selection writes the current choice", async () => {
    const { result } = renderHook(() => useLlmManager());
    // The send path can hold a reference from an earlier render.
    const persistOverrides = result.current.persistOverrides;

    act(() => result.current.updateReasoningEffort("high"));
    await act(async () => {
      await persistOverrides("session-1");
    });

    expect(updateReasoningEffortForChatSession).toHaveBeenCalledWith(
      "session-1",
      "high"
    );
  });

  test("a session persisted while unbound keeps the selection once it is adopted", async () => {
    const { result, rerender } = renderHook(
      (props: HookProps) => useLlmManager(props.session),
      { initialProps: {} }
    );

    act(() => result.current.updateReasoningEffort("high"));
    await act(async () => {
      await result.current.persistOverrides("session-1");
    });

    // The placeholder for the new session carries no override yet.
    rerender({ session: makeSession("session-1", null) });
    expect(result.current.reasoningEffort).toBe("high");

    // Another session still reads its own row.
    rerender({ session: makeSession("session-2", "low") });
    expect(result.current.reasoningEffort).toBe("low");

    // Coming back reads the row too, not the old local choice.
    rerender({ session: makeSession("session-1", null) });
    expect(result.current.reasoningEffort).toBeNull();
  });
});
