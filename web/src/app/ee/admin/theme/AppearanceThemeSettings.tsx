"use client";

import { useTranslations } from "next-intl";
import { FormField } from "@/refresh-components/form/FormField";
import {
  Button,
  Divider,
  InputTextArea,
  InputTypeIn,
  InputSwitch,
  Tag,
} from "@opal/components";
import Preview from "@/app/ee/admin/theme/Preview";
import CharacterCount from "@/refresh-components/CharacterCount";
import { Disabled } from "@opal/core";
import { useFormikContext } from "formik";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import type { PreviewHighlightTarget } from "./Preview";
import { useTierAtLeast } from "@/hooks/useTierAtLeast";
import { Tier } from "@/lib/settings/types";
import { planTagProps } from "@/lib/tier-badge";

interface AppearanceThemeSettingsProps {
  charLimits: {
    custom_greeting_message: number;
    custom_login_subtitle: number;
    custom_header_content: number;
    custom_lower_disclaimer_content: number;
    custom_popup_header: number;
    custom_popup_content: number;
    consent_screen_prompt: number;
    system_announcement_header: number;
    system_announcement_content: number;
  };
}

export interface AppearanceThemeSettingsRef {
  focusFirstError: (errors: Record<string, any>) => void;
}

export const AppearanceThemeSettings = forwardRef<
  AppearanceThemeSettingsRef,
  AppearanceThemeSettingsProps
>(function AppearanceThemeSettings({ charLimits }, ref) {
  const t = useTranslations("admin.theme");
  const tAuth = useTranslations("auth");
  const { values, errors, setFieldValue } = useFormikContext<any>();
  const enterpriseTier = useTierAtLeast(Tier.ENTERPRISE);
  const greetingMessageInputRef = useRef<HTMLInputElement>(null);
  const loginSubtitleInputRef = useRef<HTMLInputElement>(null);
  const headerContentInputRef = useRef<HTMLInputElement>(null);
  const lowerDisclaimerInputRef = useRef<HTMLTextAreaElement>(null);
  const noticeHeaderInputRef = useRef<HTMLInputElement>(null);
  const noticeContentInputRef = useRef<HTMLTextAreaElement>(null);
  const consentPromptTextAreaRef = useRef<HTMLTextAreaElement>(null);
  const customHelpLinkUrlInputRef = useRef<HTMLInputElement>(null);
  const systemAnnouncementHeaderInputRef = useRef<HTMLInputElement>(null);
  const systemAnnouncementContentInputRef = useRef<HTMLTextAreaElement>(null);
  const prevShowFirstVisitNoticeRef = useRef<boolean>(
    Boolean(values.show_first_visit_notice)
  );
  const prevEnableConsentScreenRef = useRef<boolean>(
    Boolean(values.enable_consent_screen)
  );
  const prevSystemAnnouncementEnabledRef = useRef<boolean>(
    Boolean(values.system_announcement_enabled)
  );
  const [focusedPreviewTarget, setFocusedPreviewTarget] =
    useState<PreviewHighlightTarget | null>(null);
  const [hoveredPreviewTarget, setHoveredPreviewTarget] =
    useState<PreviewHighlightTarget | null>(null);

  const highlightTarget = useMemo(
    () => focusedPreviewTarget ?? hoveredPreviewTarget,
    [focusedPreviewTarget, hoveredPreviewTarget]
  );

  const getPreviewHandlers = (target: PreviewHighlightTarget) => ({
    onFocus: () => setFocusedPreviewTarget(target),
    onBlur: () =>
      setFocusedPreviewTarget((cur) => (cur === target ? null : cur)),
    onMouseEnter: () => setHoveredPreviewTarget(target),
    onMouseLeave: () =>
      setHoveredPreviewTarget((cur) => (cur === target ? null : cur)),
  });

  // Expose focusFirstError method to parent component
  useImperativeHandle(ref, () => ({
    focusFirstError: (errors: Record<string, any>) => {
      // Focus on the first field with an error, in priority order
      const fieldRefs = [
        { name: "custom_greeting_message", ref: greetingMessageInputRef },
        { name: "custom_header_content", ref: headerContentInputRef },
        {
          name: "custom_lower_disclaimer_content",
          ref: lowerDisclaimerInputRef,
        },
        { name: "custom_login_subtitle", ref: loginSubtitleInputRef },
        { name: "custom_popup_header", ref: noticeHeaderInputRef },
        { name: "custom_popup_content", ref: noticeContentInputRef },
        { name: "consent_screen_prompt", ref: consentPromptTextAreaRef },
        { name: "custom_help_link_url", ref: customHelpLinkUrlInputRef },
        {
          name: "system_announcement_header",
          ref: systemAnnouncementHeaderInputRef,
        },
        {
          name: "system_announcement_content",
          ref: systemAnnouncementContentInputRef,
        },
      ];
      for (const field of fieldRefs) {
        if (errors[field.name] && field.ref.current) {
          field.ref.current.focus();
          // Scroll into view if needed
          field.ref.current.scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
          break;
        }
      }
    },
  }));

  useEffect(() => {
    const prev = prevShowFirstVisitNoticeRef.current;
    const next = Boolean(values.show_first_visit_notice);

    // When enabling the toggle, autofocus the "Notice Header" input.
    if (!prev && next) {
      requestAnimationFrame(() => {
        noticeHeaderInputRef.current?.focus();
      });
    }

    prevShowFirstVisitNoticeRef.current = next;
  }, [values.show_first_visit_notice]);

  useEffect(() => {
    const prev = prevEnableConsentScreenRef.current;
    const next = Boolean(values.enable_consent_screen);

    // When enabling the toggle, autofocus the "Notice Consent Prompt" input.
    if (!prev && next) {
      requestAnimationFrame(() => {
        consentPromptTextAreaRef.current?.focus();
      });
    }

    prevEnableConsentScreenRef.current = next;
  }, [values.enable_consent_screen]);

  useEffect(() => {
    const prev = prevSystemAnnouncementEnabledRef.current;
    const next = Boolean(values.system_announcement_enabled);

    // When enabling the toggle, autofocus the "Notice Header" input.
    if (!prev && next) {
      requestAnimationFrame(() => {
        systemAnnouncementHeaderInputRef.current?.focus();
      });
    }

    prevSystemAnnouncementEnabledRef.current = next;
  }, [values.system_announcement_enabled]);

  return (
    <div className="flex flex-col gap-4 w-full">
      <Preview
        className="mb-8"
        chat_footer_content={
          values.custom_lower_disclaimer_content ||
          t("preview.chatFooter.placeholder")
        }
        chat_header_content={
          values.custom_header_content || t("preview.chatHeader.placeholder")
        }
        greeting_message={
          values.custom_greeting_message || t("preview.greeting.placeholder")
        }
        highlightTarget={highlightTarget}
      />

      <FormField state={errors.custom_greeting_message ? "error" : "idle"}>
        <FormField.Label
          rightAction={
            <CharacterCount
              value={values.custom_greeting_message}
              limit={charLimits.custom_greeting_message}
            />
          }
        >
          {t("greeting.label")}
        </FormField.Label>
        <FormField.Control asChild>
          <InputTypeIn
            ref={greetingMessageInputRef}
            data-label="greeting-message-input"
            clearButton
            variant={errors.custom_greeting_message ? "error" : undefined}
            value={values.custom_greeting_message}
            {...getPreviewHandlers("greeting")}
            onChange={(e) =>
              setFieldValue("custom_greeting_message", e.target.value)
            }
          />
        </FormField.Control>
        <FormField.Description>
          {t("greeting.description")}
        </FormField.Description>
        <FormField.Message
          messages={{ error: errors.custom_greeting_message as string }}
        />
      </FormField>

      <FormField state={errors.custom_header_content ? "error" : "idle"}>
        <FormField.Label
          rightAction={
            <CharacterCount
              value={values.custom_header_content}
              limit={charLimits.custom_header_content}
            />
          }
        >
          {t("chatHeader.label")}
        </FormField.Label>
        <FormField.Control asChild>
          <InputTypeIn
            ref={headerContentInputRef}
            data-label="chat-header-input"
            clearButton
            variant={errors.custom_header_content ? "error" : undefined}
            value={values.custom_header_content}
            {...getPreviewHandlers("chat_header")}
            onChange={(e) =>
              setFieldValue("custom_header_content", e.target.value)
            }
          />
        </FormField.Control>
        <FormField.Message
          messages={{ error: errors.custom_header_content as string }}
        />
      </FormField>

      <FormField
        state={errors.custom_lower_disclaimer_content ? "error" : "idle"}
      >
        <FormField.Label
          rightAction={
            <CharacterCount
              value={values.custom_lower_disclaimer_content}
              limit={charLimits.custom_lower_disclaimer_content}
            />
          }
        >
          {t("chatFooter.label")}
        </FormField.Label>
        <FormField.Control asChild>
          <InputTextArea
            ref={lowerDisclaimerInputRef}
            data-label="chat-footer-textarea"
            rows={3}
            placeholder={t("markdownContent.placeholder")}
            variant={
              errors.custom_lower_disclaimer_content ? "error" : undefined
            }
            value={values.custom_lower_disclaimer_content}
            {...getPreviewHandlers("chat_footer")}
            onChange={(e) =>
              setFieldValue("custom_lower_disclaimer_content", e.target.value)
            }
          />
        </FormField.Control>
        <FormField.Description>
          {t("chatFooter.description")}
        </FormField.Description>
        <FormField.Message
          messages={{ error: errors.custom_lower_disclaimer_content as string }}
        />
      </FormField>

      <FormField state={errors.custom_login_subtitle ? "error" : "idle"}>
        <FormField.Label
          rightAction={
            <CharacterCount
              value={values.custom_login_subtitle}
              limit={charLimits.custom_login_subtitle}
            />
          }
        >
          {t("loginSubtitle.label")}
        </FormField.Label>
        <FormField.Control asChild>
          <InputTypeIn
            ref={loginSubtitleInputRef}
            data-label="login-subtitle-input"
            clearButton
            placeholder={tAuth("login.welcomeSubtitle.text")}
            variant={errors.custom_login_subtitle ? "error" : undefined}
            value={values.custom_login_subtitle}
            onChange={(e) =>
              setFieldValue("custom_login_subtitle", e.target.value)
            }
          />
        </FormField.Control>
        <FormField.Description>
          {t("loginSubtitle.description")}
        </FormField.Description>
        <FormField.Message
          messages={{ error: errors.custom_login_subtitle as string }}
        />
      </FormField>

      <Disabled
        disabled={!enterpriseTier}
        tooltip={t("helpLink.enterpriseTooltip")}
      >
        <div className="flex gap-2 items-start">
          <FormField
            state={errors.custom_help_link_url ? "error" : "idle"}
            className="flex-1"
          >
            <FormField.Label>
              {t("helpLink.label")}
              {!enterpriseTier && (
                <Tag {...planTagProps("enterprise")} size="sm" />
              )}
            </FormField.Label>
            <FormField.Control asChild>
              <InputTypeIn
                ref={customHelpLinkUrlInputRef}
                data-label="custom-help-link-url-input"
                clearButton
                placeholder="https://example.com"
                variant={
                  !enterpriseTier
                    ? "disabled"
                    : errors.custom_help_link_url
                      ? "error"
                      : undefined
                }
                value={values.custom_help_link_url}
                onChange={(e) =>
                  setFieldValue("custom_help_link_url", e.target.value)
                }
              />
            </FormField.Control>
            <FormField.Description>
              {t("helpLink.description")}
            </FormField.Description>
            <FormField.Message
              messages={{ error: errors.custom_help_link_url as string }}
            />
          </FormField>
          <FormField state="idle" className="flex-1">
            <FormField.Label className="invisible" aria-hidden="true">
              {t("helpLinkLabel.label")}
            </FormField.Label>
            <FormField.Control asChild>
              <InputTypeIn
                aria-label={t("helpLinkLabel.label")}
                data-label="custom-help-link-label-input"
                clearButton
                placeholder={t("helpLinkLabel.placeholder")}
                variant={!enterpriseTier ? "disabled" : undefined}
                value={values.custom_help_link_label}
                onChange={(e) =>
                  setFieldValue("custom_help_link_label", e.target.value)
                }
              />
            </FormField.Control>
          </FormField>
        </div>
      </Disabled>

      <Divider />

      <div className="flex flex-col gap-4 p-4 bg-background-tint-00 rounded-16">
        <FormField state="idle" className="gap-0">
          <div className="flex justify-between items-center">
            <FormField.Label>{t("firstVisit.label")}</FormField.Label>
            <FormField.Control>
              <InputSwitch
                aria-label={t("firstVisit.label")}
                data-label="first-visit-notice-toggle"
                checked={values.show_first_visit_notice}
                onCheckedChange={(checked) =>
                  setFieldValue("show_first_visit_notice", checked)
                }
              />
            </FormField.Control>
          </div>
          <FormField.Description>
            {t("firstVisit.description")}
          </FormField.Description>
        </FormField>

        {values.show_first_visit_notice && (
          <>
            <FormField state={errors.custom_popup_header ? "error" : "idle"}>
              <FormField.Label
                required
                rightAction={
                  <CharacterCount
                    value={values.custom_popup_header}
                    limit={charLimits.custom_popup_header}
                  />
                }
              >
                {t("noticeHeader.label")}
              </FormField.Label>
              <FormField.Control asChild>
                <InputTypeIn
                  ref={noticeHeaderInputRef}
                  data-label="notice-header-input"
                  clearButton
                  variant={errors.custom_popup_header ? "error" : undefined}
                  value={values.custom_popup_header}
                  onChange={(e) =>
                    setFieldValue("custom_popup_header", e.target.value)
                  }
                />
              </FormField.Control>
              <FormField.Message
                messages={{ error: errors.custom_popup_header as string }}
              />
            </FormField>

            <FormField state={errors.custom_popup_content ? "error" : "idle"}>
              <FormField.Label
                required
                rightAction={
                  <CharacterCount
                    value={values.custom_popup_content}
                    limit={charLimits.custom_popup_content}
                  />
                }
              >
                {t("noticeContent.label")}
              </FormField.Label>
              <FormField.Control asChild>
                <InputTextArea
                  ref={noticeContentInputRef}
                  data-label="notice-content-textarea"
                  rows={3}
                  placeholder={t("markdownContent.placeholder")}
                  variant={errors.custom_popup_content ? "error" : undefined}
                  value={values.custom_popup_content}
                  onChange={(e) =>
                    setFieldValue("custom_popup_content", e.target.value)
                  }
                />
              </FormField.Control>
              <FormField.Message
                messages={{ error: errors.custom_popup_content as string }}
              />
            </FormField>

            <FormField state="idle" className="gap-0">
              <div className="flex justify-between items-center">
                <FormField.Label>{t("consent.label")}</FormField.Label>
                <FormField.Control>
                  <InputSwitch
                    aria-label={t("consent.label")}
                    data-label="require-consent-toggle"
                    checked={values.enable_consent_screen}
                    onCheckedChange={(checked) =>
                      setFieldValue("enable_consent_screen", checked)
                    }
                  />
                </FormField.Control>
              </div>
              <FormField.Description>
                {t("consent.description")}
              </FormField.Description>
            </FormField>

            {values.enable_consent_screen && (
              <FormField
                state={errors.consent_screen_prompt ? "error" : "idle"}
              >
                <FormField.Label
                  required
                  rightAction={
                    <CharacterCount
                      value={values.consent_screen_prompt}
                      limit={charLimits.consent_screen_prompt}
                    />
                  }
                >
                  {t("consentPrompt.label")}
                </FormField.Label>
                <FormField.Control asChild>
                  <InputTextArea
                    ref={consentPromptTextAreaRef}
                    data-label="consent-prompt-textarea"
                    rows={3}
                    placeholder={t("markdownContent.placeholder")}
                    variant={errors.consent_screen_prompt ? "error" : undefined}
                    value={values.consent_screen_prompt}
                    onChange={(e) => {
                      setFieldValue("consent_screen_prompt", e.target.value);
                    }}
                  />
                </FormField.Control>
                <FormField.Message
                  messages={{ error: errors.consent_screen_prompt as string }}
                />
              </FormField>
            )}
          </>
        )}
      </div>

      <div className="flex flex-col gap-4 p-4 bg-background-tint-00 rounded-16">
        <FormField state="idle" className="gap-0">
          <div className="flex justify-between items-center">
            <FormField.Label>{t("announcement.label")}</FormField.Label>
            <FormField.Control>
              <InputSwitch
                aria-label={t("announcement.label")}
                data-label="system-announcement-toggle"
                checked={values.system_announcement_enabled}
                onCheckedChange={(checked) =>
                  setFieldValue("system_announcement_enabled", checked)
                }
              />
            </FormField.Control>
          </div>
          <FormField.Description>
            {t("announcement.description")}
          </FormField.Description>
        </FormField>

        {values.system_announcement_enabled && (
          <>
            <FormField
              state={errors.system_announcement_header ? "error" : "idle"}
            >
              <FormField.Label
                required
                rightAction={
                  <CharacterCount
                    value={values.system_announcement_header}
                    limit={charLimits.system_announcement_header}
                  />
                }
              >
                {t("noticeHeader.label")}
              </FormField.Label>
              <FormField.Control asChild>
                <InputTypeIn
                  ref={systemAnnouncementHeaderInputRef}
                  data-label="system-announcement-header-input"
                  clearButton
                  placeholder={t("announcement.header.placeholder")}
                  variant={
                    errors.system_announcement_header ? "error" : undefined
                  }
                  value={values.system_announcement_header}
                  onChange={(e) =>
                    setFieldValue("system_announcement_header", e.target.value)
                  }
                />
              </FormField.Control>
              <FormField.Message
                messages={{
                  error: errors.system_announcement_header as string,
                }}
              />
            </FormField>

            <FormField
              state={errors.system_announcement_content ? "error" : "idle"}
            >
              <FormField.Label
                required
                rightAction={
                  <CharacterCount
                    value={values.system_announcement_content}
                    limit={charLimits.system_announcement_content}
                  />
                }
              >
                {t("noticeContent.label")}
              </FormField.Label>
              <FormField.Control asChild>
                <InputTextArea
                  ref={systemAnnouncementContentInputRef}
                  data-label="system-announcement-content-textarea"
                  rows={3}
                  placeholder={t("markdownContent.placeholder")}
                  variant={
                    errors.system_announcement_content ? "error" : undefined
                  }
                  value={values.system_announcement_content}
                  onChange={(e) =>
                    setFieldValue("system_announcement_content", e.target.value)
                  }
                />
              </FormField.Control>
              <FormField.Message
                messages={{
                  error: errors.system_announcement_content as string,
                }}
              />
            </FormField>

            <FormField state="idle" className="gap-0">
              <div className="flex justify-between items-center">
                <FormField.Label>
                  {t("announcementPopup.label")}
                </FormField.Label>
                <FormField.Control>
                  <InputSwitch
                    aria-label={t("announcementPopup.label")}
                    data-label="system-announcement-popup-toggle"
                    checked={values.system_announcement_show_as_popup}
                    onCheckedChange={(checked) =>
                      setFieldValue(
                        "system_announcement_show_as_popup",
                        checked
                      )
                    }
                  />
                </FormField.Control>
              </div>
              <FormField.Description>
                {t("announcementPopup.description")}
              </FormField.Description>
            </FormField>
          </>
        )}
      </div>
    </div>
  );
});
