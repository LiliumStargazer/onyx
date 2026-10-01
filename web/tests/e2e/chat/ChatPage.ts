/**
 * Page Object Model for the main chat page (/app).
 *
 * Encapsulates locators and interactions shared across chat specs so that
 * individual tests remain declarative.
 */

import { type Page, type Locator, expect } from "@playwright/test";
import { expectElementScreenshot } from "@tests/e2e/utils/visualRegression";
import { InputBar } from "@tests/e2e/chat/InputBar";

export class ChatPage {
  readonly page: Page;
  readonly inputBar: InputBar;

  // Layout containers
  readonly container: Locator;
  readonly scrollContainer: Locator;

  // Message collections
  readonly humanMessages: Locator;
  readonly aiMessages: Locator;
  readonly usageLimitBanner: Locator;
  readonly modelLoadError: Locator;

  constructor(page: Page) {
    this.page = page;
    this.inputBar = new InputBar(page);
    this.container = page.locator("[data-main-container]");
    this.scrollContainer = page.getByTestId("chat-scroll-container");
    this.humanMessages = page.locator("#onyx-human-message");
    this.aiMessages = page.getByTestId("onyx-ai-message");
    this.usageLimitBanner = page.getByText(/you've reached the usage budget/i);
    this.modelLoadError = page.getByRole("alert").filter({
      hasText: "Could not load the Admin chat model.",
    });
  }

  humanMessage(index = 0): Locator {
    return this.humanMessages.nth(index);
  }

  aiMessage(index = 0): Locator {
    return this.aiMessages.nth(index);
  }

  async goto(sessionId?: string): Promise<void> {
    await this.page.goto(sessionId ? `/app?chatId=${sessionId}` : "/app");
    await this.page.waitForLoadState("networkidle");
    await this.inputBar.textbox.waitFor({ state: "visible", timeout: 15000 });
  }

  async expectAssistantOnly(): Promise<void> {
    await expect(this.page.getByTestId("AppSidebar/more-agents")).toHaveCount(
      0
    );
    await expect(this.page.getByTestId("agent-name-display")).toHaveCount(0);
    await expect(this.page.getByLabel("Change app mode")).toHaveCount(0);
    await expect(
      this.page.getByText("Simulated custom agent", { exact: true })
    ).toHaveCount(0);
    await this.inputBar.expectSimpleControls();
  }

  async openChatHistorySearch(): Promise<void> {
    await this.page
      .getByRole("button", { name: "Search Chats", exact: true })
      .click();
    await expect(this.page.getByRole("dialog")).toBeVisible();
    await this.page.keyboard.press("Escape");
  }

  async expectCitedSources(): Promise<void> {
    await expect(
      this.aiMessage().getByRole("button", { name: "Wiki.js", exact: true })
    ).toBeVisible();
    await this.aiMessage()
      .getByRole("button", { name: "Sources", exact: true })
      .click();
    await expect(
      this.page
        .locator("#onyx-chat-sidebar")
        .getByText("Simulated Wiki page", { exact: true })
        .first()
    ).toBeVisible();
  }

  async gotoAgentUrl(path: string): Promise<void> {
    await this.page.goto(path);
    await this.expectAssistantRedirect();
  }

  async expectAssistantRedirect(): Promise<void> {
    await expect(this.page).toHaveURL(/\/app$/);
    await this.inputBar.textbox.waitFor({ state: "visible" });
  }

  async gotoSessionPrompt(sessionId: string, message: string): Promise<void> {
    const params = new URLSearchParams({
      chatId: sessionId,
      "user-prompt": message,
      "send-on-load": "true",
    });
    await this.page.goto(`/app?${params}`);
    await this.inputBar.textbox.waitFor({ state: "visible" });
  }

  async expectAdminAgentsHidden(): Promise<void> {
    await this.page.goto("/admin/chat-preferences");
    await expect(this.page.getByLabel("admin-page-title")).toHaveText(
      "Chat Preferences"
    );
    await expect(
      this.page.getByRole("link", { name: "Agents", exact: true })
    ).toHaveCount(0);
  }

  async expectNoModelSelectors(): Promise<void> {
    await expect(this.page.getByTestId("model-selector")).toHaveCount(0);
    await expect(
      this.page.getByRole("button", { name: "Add Model", exact: true })
    ).toHaveCount(0);
  }

  async expectModelLoadError(): Promise<void> {
    await expect(this.modelLoadError).toBeVisible();
    await expect(this.inputBar.textbox).toHaveAttribute(
      "contenteditable",
      "false"
    );
  }

  async retryModelLoad(): Promise<void> {
    await this.modelLoadError
      .getByRole("button", { name: "Try again", exact: true })
      .click();
    await expect(this.modelLoadError).toHaveCount(0);
    await expect(this.inputBar.textbox).toHaveAttribute(
      "contenteditable",
      "true"
    );
  }

  async regenerate(index = 0): Promise<void> {
    await this.aiMessage(index).hover();
    await this.aiMessage(index).getByTestId("AgentMessage/regenerate").click();
    await expect(this.page.getByRole("dialog")).toHaveCount(0);
  }

  async scrollTo(position: "top" | "bottom"): Promise<void> {
    await this.scrollContainer.evaluate(async (el, pos) => {
      el.scrollTo({ top: pos === "top" ? 0 : el.scrollHeight });
      await new Promise<void>((r) => requestAnimationFrame(() => r()));
    }, position);
  }

  async screenshotContainer(name: string): Promise<void> {
    await expect(this.container).toBeVisible();
    if ((await this.scrollContainer.count()) > 0) {
      await this.scrollTo("bottom");
    }
    await expectElementScreenshot(this.container, { name });
  }

  /**
   * Captures two screenshots of the chat container for long-content tests:
   * one scrolled to the top and one scrolled to the bottom. Ensures
   * consistent scroll positions regardless of whether the page was just
   * navigated to (top) or just finished streaming (bottom).
   */
  async screenshotContainerTopAndBottom(name: string): Promise<void> {
    await expect(this.container).toBeVisible();

    await this.scrollTo("top");
    await expectElementScreenshot(this.container, { name: `${name}-top` });

    await this.scrollTo("bottom");
    await expectElementScreenshot(this.container, { name: `${name}-bottom` });
  }

  // ---------------------------------------------------------------------------
  // Message assertions
  // ---------------------------------------------------------------------------

  async expectHumanMessage(text: string, index = 0): Promise<void> {
    await expect(this.humanMessage(index)).toContainText(text);
  }

  async expectNoHumanMessages(): Promise<void> {
    await expect(this.humanMessages).toHaveCount(0);
  }

  async sendUntilUsageLimit(maxTurns: number): Promise<void> {
    for (
      let turn = 0;
      turn < maxTurns && !(await this.usageLimitBanner.isVisible());
      turn++
    ) {
      await this.inputBar.fill(`write a few sentences about topic ${turn}`);
      await this.inputBar.send();
      await Promise.race([
        this.usageLimitBanner
          .waitFor({ state: "visible", timeout: 45_000 })
          .catch(() => {}),
        this.aiMessage(turn)
          .waitFor({ state: "visible", timeout: 45_000 })
          .catch(() => {}),
      ]);
    }
  }

  async expectAccountUsageLimit(): Promise<void> {
    await expect(this.usageLimitBanner).toBeVisible();
    await expect(this.page.getByText(/your account/i)).toBeVisible();
  }
}
