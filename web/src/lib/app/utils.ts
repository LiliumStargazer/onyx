import { SEARCH_PARAM_NAMES } from "@/app/app/services/searchParams";
import { DEFAULT_AGENT_ID, SIMPLIFIED_CHAT_ENABLED } from "@/lib/constants";

/**
 * Where `/app` should send a request that names an agent explicitly, or
 * `null` when the query is already fine.
 *
 * Simplified chat routes every named agent to Assistant. Upstream chat only
 * normalizes agent 0. Keep the remaining query parameters.
 */
export function defaultAgentRedirectTarget(
  searchParams: Record<string, string>
): "/app" | `/app?${string}` | null {
  const agentId = searchParams[SEARCH_PARAM_NAMES.AGENT_ID];
  if (
    agentId === undefined ||
    (!SIMPLIFIED_CHAT_ENABLED && agentId !== String(DEFAULT_AGENT_ID))
  ) {
    return null;
  }

  const rest = new URLSearchParams(searchParams);
  rest.delete(SEARCH_PARAM_NAMES.AGENT_ID);
  const query = rest.toString();

  return query ? `/app?${query}` : "/app";
}
