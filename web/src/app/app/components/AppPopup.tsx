"use client";

import { Modal } from "@opal/components";
import { useSettings } from "@/lib/settings/hooks";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import { FormField } from "@/refresh-components/form/FormField";
import { InputCheckbox } from "@opal/components";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { transformLinkUri } from "@/lib/utils";
import { Logo } from "@/lib/app/components";
import { useTranslations } from "next-intl";

const ALL_USERS_INITIAL_POPUP_FLOW_COMPLETED =
  "allUsersInitialPopupFlowCompleted";

export function AppPopup() {
  const t = useTranslations("chat.popup");
  const [completedFlow, setCompletedFlow] = useState(true);
  const [showConsentError, setShowConsentError] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);

  useEffect(() => {
    setCompletedFlow(
      localStorage.getItem(ALL_USERS_INITIAL_POPUP_FLOW_COMPLETED) === "true"
    );
  }, []);

  const settings = useSettings();
  const isConsentScreen = settings.enterprise?.enable_consent_screen;

  if (
    !settings.enterprise?.custom_popup_content ||
    completedFlow ||
    !settings.enterprise?.show_first_visit_notice
  ) {
    return null;
  }

  const popupTitle = settings.enterprise?.custom_popup_header;

  const popupContent = settings.enterprise?.custom_popup_content;

  return (
    <Modal open onOpenChange={() => {}}>
      <Modal.Content width="sm" height="lg">
        <Modal.Header
          icon={Logo}
          title={popupTitle || t("header.title", { appName: settings.appName })}
        />
        <Modal.Body>
          <div className="overflow-y-auto text-start">
            <ReactMarkdown
              className="prose prose-neutral dark:prose-invert max-w-full"
              components={{
                a: ({ node, children, ...props }) => (
                  <a
                    {...props}
                    className="text-link hover:text-link-hover"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {children}
                  </a>
                ),
                p: ({ node, ...props }) => (
                  <Text as="p" mainUiBody text03 {...props} />
                ),
                strong: ({ node, ...props }) => (
                  <Text mainUiBody text03 {...props} />
                ),
                h1: ({ node, ...props }) => (
                  <Text as="p" headingH1 text03 {...props} />
                ),
                h2: ({ node, ...props }) => (
                  <Text as="p" headingH2 text03 {...props} />
                ),
                h3: ({ node, ...props }) => (
                  <Text as="p" headingH3 text03 {...props} />
                ),
                li: ({ node, ...props }) => (
                  <Text as="li" mainUiBody text03 {...props} />
                ),
              }}
              remarkPlugins={[remarkGfm]}
              urlTransform={transformLinkUri}
            >
              {popupContent}
            </ReactMarkdown>
            {isConsentScreen && settings.enterprise?.consent_screen_prompt && (
              <FormField
                state={showConsentError ? "error" : "idle"}
                className="mt-6"
              >
                <div className="flex items-center gap-1">
                  <FormField.Control>
                    <InputCheckbox
                      aria-label={t("consentCheckbox.label")}
                      checked={consentChecked}
                      onCheckedChange={(checked) => {
                        setConsentChecked(checked);
                        if (checked) {
                          setShowConsentError(false);
                        }
                      }}
                    />
                  </FormField.Control>
                  <FormField.Label>
                    <ReactMarkdown
                      className="prose prose-neutral dark:prose-invert max-w-full"
                      components={{
                        a: ({ node, children, ...props }) => (
                          <a
                            {...props}
                            className="text-link hover:text-link-hover"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {children}
                          </a>
                        ),
                        p: ({ node, ...props }) => (
                          <Text
                            as="p"
                            mainUiBody
                            text04
                            className="my-0!" //dont remove the my-0! class, it's important for the markdown to render without any alignment issues
                            {...props}
                          />
                        ),
                        strong: ({ node, ...props }) => (
                          <Text mainUiBody text04 {...props} />
                        ),
                        li: ({ node, ...props }) => (
                          <Text as="li" mainUiBody text04 {...props} />
                        ),
                      }}
                      remarkPlugins={[remarkGfm]}
                      urlTransform={transformLinkUri}
                    >
                      {settings.enterprise.consent_screen_prompt}
                    </ReactMarkdown>
                  </FormField.Label>
                </div>
                <FormField.Message
                  messages={{ error: t("consentRequired.error") }}
                />
              </FormField>
            )}
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button
            onClick={() => {
              if (isConsentScreen && !consentChecked) {
                setShowConsentError(true);
                return;
              }
              localStorage.setItem(
                ALL_USERS_INITIAL_POPUP_FLOW_COMPLETED,
                "true"
              );
              setCompletedFlow(true);
            }}
          >
            {t("startButton.label")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
