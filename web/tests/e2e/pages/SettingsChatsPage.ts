import { expect, type Page } from "@playwright/test";

export class SettingsChatsPage {
  constructor(readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/app/settings/chat-preferences");
    await expect(
      this.page.getByText("Chat Auto-scroll", { exact: true })
    ).toBeVisible();
  }

  async expectNoModelSelector(): Promise<void> {
    await expect(
      this.page.getByText("Default Model", { exact: true })
    ).toHaveCount(0);
    await expect(this.page.getByTestId("model-selector")).toHaveCount(0);
  }
}
