import { expect, test } from "@playwright/test";

test.use({ storageState: "admin_auth.json" });

test("Google provider offers an explicit link to the signed-in admin", async ({
  page,
}) => {
  await page.route("**/api/admin/sso/provider", async (route) => {
    await route.fulfill({
      json: [
        {
          id: 17,
          name: "workspace",
          display_name: "Workspace",
          provider_type: "GOOGLE_OAUTH",
          enabled: true,
          redirect_uri:
            "http://localhost:3000/api/auth/oidc/workspace/callback",
          allowed_email_domains: ["corp.test"],
          config: {
            client_id: "client",
            directory_auth_mode: "service_account",
          },
        },
      ],
    });
  });
  await page.route("**/api/auth/oidc/workspace/authorize?*", async (route) => {
    await route.fulfill({
      json: { authorization_url: "/admin/sso-providers?link-started=1" },
    });
  });

  await page.goto("/admin/sso-providers");
  await page.getByRole("button", { name: "Link my Google account" }).click();
  await expect(page).toHaveURL(/link-started=1/);
});
