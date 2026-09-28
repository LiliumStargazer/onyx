"use client";

import useSWR from "swr";
import { usePathname } from "next/navigation";
import useCCPairs from "@/hooks/useCCPairs";
import { errorHandlingFetcher, isNotFoundError } from "@/lib/fetcher";
import { SWR_KEYS } from "@/lib/swr-keys";
import { isAuthPath } from "@/lib/auth/paths";
import {
  ApplicationStatus,
  AppSettings,
  EnterpriseSettings,
  QueryHistoryType,
  Settings,
} from "@/lib/settings/types";
import { APP_NAME, EE_ENABLED } from "@/lib/constants";

const SETTINGS_ERROR_RETRY_INTERVAL = 5_000;

const DEFAULT_SETTINGS: Settings = {
  auto_scroll: true,
  application_status: ApplicationStatus.ACTIVE,
  gpu_enabled: false,
  maximum_chat_retention_days: null,
  notifications: [],
  needs_reindexing: false,
  anonymous_user_enabled: false,
  invite_only_enabled: false,
  deep_research_enabled: true,
  multi_model_chat_enabled: true,
  temperature_override_enabled: true,
  reasoning_override_enabled: true,
  query_history_type: QueryHistoryType.NORMAL,
};

// A CE backend never registers the enterprise-settings route, so its 404
// means no enterprise settings, not an outage: no error and no retry.
const isEnterpriseSettingsMissing = isNotFoundError;

/**
 * The single settings hook. Returns a fully-derived `AppSettings` object that
 * merges core settings and enterprise settings into one consistent shape.
 *
 * Derived fields (`appName`, `vectorDbEnabled`) are pre-computed so callers
 * never have to re-derive them or fetch enterprise settings separately.
 */
export function useSettings(): AppSettings {
  // Skip core settings on /auth/* routes: unauthenticated callers 403 there, and
  // the login shell only needs enterprise-derived `appName` (fetched below).
  const onAuthPath = isAuthPath(usePathname());

  const {
    data: rawSettings,
    error: settingsError,
    isLoading: settingsLoading,
  } = useSWR<Settings, Error>(
    onAuthPath ? null : SWR_KEYS.settings,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      revalidateIfStale: false,
      dedupingInterval: 30_000,
      errorRetryInterval: SETTINGS_ERROR_RETRY_INTERVAL,
    }
  );

  const core = rawSettings ?? DEFAULT_SETTINGS;
  // Auth pages need branding pre-sign-in but standard web images lack the EE
  // flag, so probe the endpoint.
  const shouldFetchEnterprise =
    EE_ENABLED ||
    onAuthPath ||
    (!settingsLoading && !settingsError && core.ee_features_enabled !== false);

  const {
    data: enterprise,
    error: enterpriseError,
    isLoading: enterpriseLoading,
  } = useSWR<EnterpriseSettings, Error>(
    shouldFetchEnterprise ? SWR_KEYS.enterpriseSettings : null,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      revalidateIfStale: false,
      dedupingInterval: 30_000,
      errorRetryInterval: SETTINGS_ERROR_RETRY_INTERVAL,
      shouldRetryOnError: (err) => !isEnterpriseSettingsMissing(err),
    }
  );

  return {
    ...core,
    enterprise: enterprise ?? null,
    appName: APP_NAME,
    vectorDbEnabled:
      !settingsLoading && !settingsError && core.vector_db_enabled !== false,
    isLoading:
      settingsLoading || (shouldFetchEnterprise ? enterpriseLoading : false),
    error:
      settingsError ??
      (isEnterpriseSettingsMissing(enterpriseError)
        ? undefined
        : enterpriseError),
  };
}

/**
 * Returns `true` when search mode is actually usable by the current user.
 *
 * This is a cross-cutting hook: it joins `useSettings()` (two settings
 * endpoints) with connector state (`useCCPairs`). It is intentionally kept
 * separate from `useSettings()` so that the connector list fetch only fires in
 * the small number of components that actually need it.
 */
export function useIsSearchModeAvailable(): boolean {
  const { vectorDbEnabled, search_ui_enabled } = useSettings();
  const { ccPairs } = useCCPairs(vectorDbEnabled);
  return search_ui_enabled !== false && ccPairs.length > 0;
}
