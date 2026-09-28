import {
  R2Icon,
  S3Icon,
  GoogleStorageIcon,
  BraintrustIcon,
  BoxIcon,
} from "@/components/icons/icons";
import { ValidSources } from "@/lib/types";
import { SourceCategory, SourceMetadata } from "@/lib/search/types";
import { Agent } from "@/lib/agents/types";
import React from "react";
import { SvgFileText, SvgGlobe, SvgUploadCloud, SvgMail } from "@opal/icons";
import {
  SvgAirtable,
  SvgAsana,
  SvgAxero,
  SvgBitbucket,
  SvgBookstack,
  SvgCanvas,
  SvgClickup,
  SvgCoda,
  SvgConfluence,
  SvgDiscord,
  SvgDiscourse,
  SvgDocument360,
  SvgDropbox,
  SvgDrupal,
  SvgEgnyte,
  SvgFireflies,
  SvgFreshdesk,
  SvgGitbook,
  SvgGithub,
  SvgGitlab,
  SvgGmail,
  SvgGong,
  SvgGoogleDrive,
  SvgGoogleSites,
  SvgGuru,
  SvgHighspot,
  SvgHubspot,
  SvgJira,
  SvgLinear,
  SvgLoopio,
  SvgLumapps,
  SvgMediawiki,
  SvgNotion,
  SvgOracle,
  SvgOutline,
  SvgOutlook,
  SvgProductboard,
  SvgSalesforce,
  SvgSharepoint,
  SvgSlab,
  SvgSlack,
  SvgTeams,
  SvgTestrail,
  SvgWikipedia,
  SvgXenforo,
  SvgZendesk,
  SvgZulip,
} from "@opal/logos";

interface PartialSourceMetadata {
  icon: React.FC<{ size?: number; className?: string }>;
  displayName: string;
  category: SourceCategory;
  isPopular?: boolean;
  oauthSupported?: boolean;
  federated?: boolean;
  federatedTooltip?: string;
  // federated connectors store the base source type if it's a source
  // that has both indexed connectors and federated connectors
  baseSourceType?: ValidSources;
}

type SourceMap = {
  [K in ValidSources | "federated_slack"]: PartialSourceMetadata;
};

const slackMetadata = {
  icon: SvgSlack,
  displayName: "Slack",
  category: SourceCategory.Messaging,
  isPopular: true,
  oauthSupported: true,
  // Federated Slack is available as an option but not the default
  federated: true,
  federatedTooltip:
    "⚠️ WARNING: Federated Slack results in significantly greater latency and lower search quality.",
  baseSourceType: "slack",
};

export const SOURCE_METADATA_MAP: SourceMap = {
  // Knowledge Base & Wikis
  confluence: {
    icon: SvgConfluence,
    displayName: "Confluence",
    category: SourceCategory.Wiki,
    oauthSupported: true,
    isPopular: true,
  },
  lumapps: {
    icon: SvgLumapps,
    displayName: "LumApps",
    category: SourceCategory.Wiki,
  },
  sharepoint: {
    icon: SvgSharepoint,
    displayName: "Sharepoint",
    category: SourceCategory.Wiki,
    isPopular: true,
  },
  coda: {
    icon: SvgCoda,
    displayName: "Coda",
    category: SourceCategory.Wiki,
  },
  notion: {
    icon: SvgNotion,
    displayName: "Notion",
    category: SourceCategory.Wiki,
  },
  bookstack: {
    icon: SvgBookstack,
    displayName: "BookStack",
    category: SourceCategory.Wiki,
  },
  document360: {
    icon: SvgDocument360,
    displayName: "Document360",
    category: SourceCategory.Wiki,
  },
  discourse: {
    icon: SvgDiscourse,
    displayName: "Discourse",
    category: SourceCategory.Wiki,
  },
  gitbook: {
    icon: SvgGitbook,
    displayName: "GitBook",
    category: SourceCategory.Wiki,
  },
  slab: {
    icon: SvgSlab,
    displayName: "Slab",
    category: SourceCategory.Wiki,
  },
  outline: {
    icon: SvgOutline,
    displayName: "Outline",
    category: SourceCategory.Wiki,
  },
  google_sites: {
    icon: SvgGoogleSites,
    displayName: "Google Sites",
    category: SourceCategory.Wiki,
  },
  guru: {
    icon: SvgGuru,
    displayName: "Guru",
    category: SourceCategory.Wiki,
  },
  wikijs: {
    icon: SvgFileText,
    displayName: "Wiki.js",
    category: SourceCategory.Wiki,
  },
  mediawiki: {
    icon: SvgMediawiki,
    displayName: "MediaWiki",
    category: SourceCategory.Wiki,
  },
  axero: {
    icon: SvgAxero,
    displayName: "Axero",
    category: SourceCategory.Wiki,
  },
  wikipedia: {
    icon: SvgWikipedia,
    displayName: "Wikipedia",
    category: SourceCategory.Wiki,
  },
  canvas: {
    icon: SvgCanvas,
    displayName: "Canvas",
    category: SourceCategory.Wiki,
  },

  // Cloud Storage
  google_drive: {
    icon: SvgGoogleDrive,
    displayName: "Google Drive",
    category: SourceCategory.Storage,
    oauthSupported: true,
    isPopular: true,
  },
  box: {
    icon: BoxIcon,
    displayName: "Box",
    category: SourceCategory.Storage,
  },
  dropbox: {
    icon: SvgDropbox,
    displayName: "Dropbox",
    category: SourceCategory.Storage,
  },
  s3: {
    icon: S3Icon,
    displayName: "S3",
    category: SourceCategory.Storage,
  },
  google_cloud_storage: {
    icon: GoogleStorageIcon,
    displayName: "Google Storage",
    category: SourceCategory.Storage,
  },
  egnyte: {
    icon: SvgEgnyte,
    displayName: "Egnyte",
    category: SourceCategory.Storage,
  },
  oci_storage: {
    icon: SvgOracle,
    displayName: "Oracle Storage",
    category: SourceCategory.Storage,
  },
  r2: {
    icon: R2Icon,
    displayName: "R2",
    category: SourceCategory.Storage,
  },

  // Ticketing & Task Management
  jira: {
    icon: SvgJira,
    displayName: "Jira",
    category: SourceCategory.TicketingAndTaskManagement,
    isPopular: true,
  },
  zendesk: {
    icon: SvgZendesk,
    displayName: "Zendesk",
    category: SourceCategory.TicketingAndTaskManagement,
    isPopular: true,
  },
  airtable: {
    icon: SvgAirtable,
    displayName: "Airtable",
    category: SourceCategory.TicketingAndTaskManagement,
  },
  linear: {
    icon: SvgLinear,
    displayName: "Linear",
    category: SourceCategory.TicketingAndTaskManagement,
  },
  freshdesk: {
    icon: SvgFreshdesk,
    displayName: "Freshdesk",
    category: SourceCategory.TicketingAndTaskManagement,
  },
  asana: {
    icon: SvgAsana,
    displayName: "Asana",
    category: SourceCategory.TicketingAndTaskManagement,
  },
  clickup: {
    icon: SvgClickup,
    displayName: "Clickup",
    category: SourceCategory.TicketingAndTaskManagement,
  },
  productboard: {
    icon: SvgProductboard,
    displayName: "Productboard",
    category: SourceCategory.TicketingAndTaskManagement,
  },
  testrail: {
    icon: SvgTestrail,
    displayName: "TestRail",
    category: SourceCategory.TicketingAndTaskManagement,
  },

  // Messaging
  slack: slackMetadata,
  federated_slack: slackMetadata,
  teams: {
    icon: SvgTeams,
    displayName: "Teams",
    category: SourceCategory.Messaging,
  },
  outlook: {
    icon: SvgOutlook,
    displayName: "Outlook",
    category: SourceCategory.Messaging,
  },
  gmail: {
    icon: SvgGmail,
    displayName: "Gmail",
    category: SourceCategory.Messaging,
  },
  drupal_wiki: {
    icon: SvgDrupal,
    displayName: "Drupal Wiki",
    category: SourceCategory.Wiki,
  },
  imap: {
    icon: SvgMail,
    displayName: "Email",
    category: SourceCategory.Messaging,
  },
  discord: {
    icon: SvgDiscord,
    displayName: "Discord",
    category: SourceCategory.Messaging,
  },
  xenforo: {
    icon: SvgXenforo,
    displayName: "Xenforo",
    category: SourceCategory.Messaging,
  },
  zulip: {
    icon: SvgZulip,
    displayName: "Zulip",
    category: SourceCategory.Messaging,
  },

  // Sales
  salesforce: {
    icon: SvgSalesforce,
    displayName: "Salesforce",
    category: SourceCategory.Sales,
    isPopular: true,
  },
  hubspot: {
    icon: SvgHubspot,
    displayName: "HubSpot",
    category: SourceCategory.Sales,
    isPopular: true,
  },
  gong: {
    icon: SvgGong,
    displayName: "Gong",
    category: SourceCategory.Sales,
    isPopular: true,
  },
  fireflies: {
    icon: SvgFireflies,
    displayName: "Fireflies",
    category: SourceCategory.Sales,
  },
  highspot: {
    icon: SvgHighspot,
    displayName: "Highspot",
    category: SourceCategory.Sales,
  },
  loopio: {
    icon: SvgLoopio,
    displayName: "Loopio",
    category: SourceCategory.Sales,
  },

  // Code Repository
  github: {
    icon: SvgGithub,
    displayName: "Github",
    category: SourceCategory.CodeRepository,
    isPopular: true,
  },
  gitlab: {
    icon: SvgGitlab,
    displayName: "Gitlab",
    category: SourceCategory.CodeRepository,
  },
  bitbucket: {
    icon: SvgBitbucket,
    displayName: "Bitbucket",
    category: SourceCategory.CodeRepository,
  },

  // Others
  web: {
    icon: SvgGlobe,
    displayName: "Web",
    category: SourceCategory.Other,
    isPopular: true,
  },
  file: {
    icon: SvgFileText,
    displayName: "File",
    category: SourceCategory.Other,
    isPopular: true,
  },
  user_file: {
    icon: SvgUploadCloud,
    displayName: "Uploaded Files",
    category: SourceCategory.Other,
    isPopular: false, // Needs to be false to hide from the Add Connector page
  },
  braintrust: {
    icon: BraintrustIcon,
    displayName: "Braintrust",
    category: SourceCategory.AiObservability,
  },

  // Other
  ingestion_api: {
    icon: SvgGlobe,
    displayName: "Ingestion",
    category: SourceCategory.Other,
  },

  // Craft-specific sources
  craft_file: {
    icon: SvgFileText,
    displayName: "Your Files",
    category: SourceCategory.Other,
  },

  // Placeholder (non-null default)
  not_applicable: {
    icon: SvgGlobe,
    displayName: "Not Applicable",
    category: SourceCategory.Other,
  },
  mock_connector: {
    icon: SvgGlobe,
    displayName: "Mock Connector",
    category: SourceCategory.Other,
  },
} as SourceMap;

function fillSourceMetadata(
  partialMetadata: PartialSourceMetadata,
  internalName: ValidSources
): SourceMetadata {
  return {
    internalName: partialMetadata.baseSourceType || internalName,
    ...partialMetadata,
    adminUrl: `/admin/connectors/${internalName}`,
  };
}

export function getSourceMetadata(sourceType: ValidSources): SourceMetadata {
  const partialMetadata = SOURCE_METADATA_MAP[sourceType];

  // Fallback to not_applicable if sourceType not found in map
  if (!partialMetadata) {
    return fillSourceMetadata(
      SOURCE_METADATA_MAP[ValidSources.NotApplicable],
      ValidSources.NotApplicable
    );
  }

  return fillSourceMetadata(partialMetadata, sourceType);
}

export function listSourceMetadata(): SourceMetadata[] {
  /* This gives back all the viewable / common sources, primarily for
  display in the Add Connector page */
  const entries = Object.entries(SOURCE_METADATA_MAP)
    .filter(
      ([source, _]) =>
        source !== "not_applicable" &&
        source !== "ingestion_api" &&
        source !== "mock_connector" &&
        // use the "regular" slack connector when listing
        source !== "federated_slack" &&
        // user_file is for internal use (projects), not the Add Connector page
        source !== "user_file" &&
        // craft_file backs the Craft user library, which has its own upload UI
        source !== "craft_file"
    )
    .map(([source, metadata]) => {
      return fillSourceMetadata(metadata, source as ValidSources);
    });
  return entries;
}

export function isValidSource(sourceType: string): boolean {
  return Object.keys(SOURCE_METADATA_MAP).includes(sourceType);
}

export function getSourceDisplayName(sourceType: ValidSources): string | null {
  return getSourceMetadata(sourceType).displayName;
}

/** The configured sources, one entry per source type. */
export function getConfiguredSources(
  availableSources: ValidSources[]
): Array<SourceMetadata & { originalName: string; uniqueKey: string }> {
  const seen = new Set<string>();
  const result: Array<
    SourceMetadata & { originalName: string; uniqueKey: string }
  > = [];

  for (const sourceName of availableSources) {
    const cleanName = sourceName.replace("federated_", "") as ValidSources;
    if (seen.has(cleanName)) continue;
    seen.add(cleanName);

    const metadata = getSourceMetadata(cleanName);
    if (metadata.internalName === ValidSources.NotApplicable) continue;

    result.push({
      ...metadata,
      originalName: sourceName,
      uniqueKey: cleanName,
    });
  }
  return result;
}
