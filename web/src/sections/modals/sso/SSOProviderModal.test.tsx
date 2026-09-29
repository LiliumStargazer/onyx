import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import type { SSOProviderResponse } from "@/lib/sso/interfaces";
import { updateSSOProvider } from "@/lib/sso/svc";
import { SSOProviderModal } from "@/sections/modals/sso/SSOProviderModal";

jest.mock("@/lib/sso/svc", () => ({
  updateSSOProvider: jest.fn(),
}));

jest.mock("@/lib/sso/hooks", () => ({
  useSupportedSSOProviderTypes: () => ({
    providerTypes: ["GOOGLE_OAUTH"],
    isLoading: false,
  }),
}));

const configuredGoogleProvider: SSOProviderResponse = {
  id: 17,
  name: "workspace",
  display_name: "Workspace",
  provider_type: "GOOGLE_OAUTH",
  enabled: true,
  allowed_email_domains: ["corp.test"],
  config: {
    client_id: "client",
    client_secret: "abcd••••••efgh",
    ou_role_map: '{"/Staff":"interni"}',
    directory_auth_mode: "service_account",
    directory_service_account_json: "••••••••••••",
  },
  redirect_uri: "http://localhost:3000/api/auth/oidc/workspace/callback",
};

afterEach(() => jest.clearAllMocks());

test.each([
  { name: "allowed domain", domains: ["corp.test"] },
  { name: "missing domain", domains: [] },
])(
  "allows an update attempt for a Google provider with $name",
  async ({ domains }) => {
    const user = setupUser();
    render(
      <SSOProviderModal
        provider={{
          ...configuredGoogleProvider,
          allowed_email_domains: domains,
        }}
        onSaved={async () => {}}
      />
    );

    const update = screen.getByRole("button", { name: "Update" });
    expect(update).toBeDisabled();
    await user.type(screen.getByPlaceholderText("Company A"), " updated");
    await waitFor(() => expect(update).toBeEnabled());

    if (domains.length === 0) {
      expect(
        screen.getAllByText("List at least one email domain that may sign in")
      ).toHaveLength(2);
      await user.click(update);
      expect(updateSSOProvider).not.toHaveBeenCalled();
      await user.type(
        screen.getByPlaceholderText("Add a domain (e.g. onyx.app)"),
        "corp.test{Enter}"
      );
    }

    jest.mocked(updateSSOProvider).mockResolvedValue(configuredGoogleProvider);
    await user.click(update);
    await waitFor(() =>
      expect(updateSSOProvider).toHaveBeenCalledWith(
        17,
        expect.objectContaining({ allowed_email_domains: ["corp.test"] })
      )
    );
  }
);
