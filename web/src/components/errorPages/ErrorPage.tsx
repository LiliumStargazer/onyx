import { useTranslations } from "next-intl";
import ErrorPageLayout from "@/components/errorPages/ErrorPageLayout";
import Text from "@/refresh-components/texts/Text";
import { SvgAlertCircle } from "@opal/icons";
import { useSettings } from "@/lib/settings/hooks";

export default function Error() {
  const t = useTranslations("common.errorPages");
  const { appName } = useSettings();
  return (
    <ErrorPageLayout>
      <div className="flex flex-row items-center gap-2">
        <Text as="p" headingH2>
          {t("configError.heading.title")}
        </Text>
        <SvgAlertCircle className="w-6 h-6 stroke-text-04" />
      </div>

      <Text as="p" text03>
        {t("configError.heading.description", { appName })}
      </Text>

      <Text as="p" text03>
        {t("configError.adminHint.text")}
      </Text>
    </ErrorPageLayout>
  );
}
