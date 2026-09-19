import type { SdlcPhase } from "./workbench";

/**
 * The integration registry.
 *
 * Meridian Loom is a delivery tool, so the systems it connects to are the
 * ones delivery actually runs on: source and review, planning, pipelines,
 * runtimes, observability, messaging, cloud and scheduling. This file is the
 * catalogue's presentation contract — names, categories, the fields a
 * connection needs, and what each read operation returns. It deliberately
 * holds no URLs, headers or credentials: the wire shape lives host-side in
 * `extension/src/workbench/integrations.ts`, and secrets never leave the OS
 * keychain.
 *
 * Two honesty rules run through the whole surface:
 *
 *  1. A connection is *probed*, never assumed. Every definition names what a
 *     successful probe actually proves, because "connected" with no evidence
 *     behind it is the most common lie an integrations page tells.
 *  2. Reads are reads. Nothing here writes to, triggers or mutates a
 *     connected system. A tool that can restart your cluster should say so
 *     before it can, and none of these can.
 */

export type IntegrationCategory =
  | "source"
  | "planning"
  | "pipeline"
  | "runtime"
  | "observability"
  | "messaging"
  | "cloud"
  | "quality"
  | "api"
  | "scheduling"
  | "browser";

export const INTEGRATION_CATEGORY_LABELS: Readonly<
  Record<IntegrationCategory, string>
> = {
  source: "Source & review",
  planning: "Planning & tracking",
  pipeline: "Build & pipelines",
  runtime: "Runtimes & containers",
  observability: "Observability",
  messaging: "Messaging",
  cloud: "Cloud",
  quality: "Code quality",
  api: "API tooling",
  scheduling: "Scheduling",
  browser: "Browser",
};

/** How a connection authenticates. Shown to the user before they configure. */
export type IntegrationAuth =
  | "token"
  | "basic"
  | "key-pair"
  | "cli-context"
  | "none";

export const INTEGRATION_AUTH_LABELS: Readonly<
  Record<IntegrationAuth, string>
> = {
  token: "Personal access token",
  basic: "User and token",
  "key-pair": "API key and application key",
  "cli-context": "Uses the CLI already signed in on this machine",
  none: "No credentials",
};

/** Whether Meridian reaches the system over HTTP or through its local CLI. */
export type IntegrationTransportKind = "http" | "cli";

export interface IntegrationField {
  key: string;
  label: string;
  hint: string;
  /** `secret` fields go to the OS keychain and are never read back. */
  kind: "text" | "url" | "secret";
  required: boolean;
  placeholder?: string;
}

export interface IntegrationOperation {
  id: string;
  label: string;
  /** One line: what this read returns, in the connected system's own words. */
  summary: string;
  /** Column headers for the returned rows. */
  columns: readonly string[];
  /** Plural noun for counts and the empty state ("12 pipelines"). */
  unit: string;
}

export interface IntegrationDefinition {
  id: string;
  name: string;
  category: IntegrationCategory;
  blurb: string;
  /**
   * The card's signal colour. Brand-adjacent rather than a brand asset: this
   * is a hue that makes the card recognisable at a glance, not a logo.
   */
  hue: string;
  auth: IntegrationAuth;
  transport: IntegrationTransportKind;
  /** The binary a `cli` integration needs, named so a failure is diagnosable. */
  binary?: string;
  fields: readonly IntegrationField[];
  /** What a green probe actually establishes. Never "it works". */
  probeLabel: string;
  operations: readonly IntegrationOperation[];
  docsUrl: string;
  /** SDLC phases this system informs, used to suggest agent bindings. */
  phases: readonly SdlcPhase[];
}

const url = (
  key: string,
  label: string,
  hint: string,
  placeholder: string,
): IntegrationField => ({
  key,
  label,
  hint,
  kind: "url",
  required: true,
  placeholder,
});
const text = (
  key: string,
  label: string,
  hint: string,
  placeholder = "",
  required = false,
): IntegrationField => ({ key, label, hint, kind: "text", required, placeholder });
const secret = (
  key: string,
  label: string,
  hint: string,
  required = true,
): IntegrationField => ({ key, label, hint, kind: "secret", required });

export const INTEGRATIONS: readonly IntegrationDefinition[] = [
  // ——— source & review ———
  {
    id: "gitlab",
    name: "GitLab",
    category: "source",
    blurb: "Pipelines, merge requests and issues for the project you name.",
    hue: "#e2542c",
    auth: "token",
    transport: "http",
    fields: [
      url("baseUrl", "Instance URL", "Self-managed or gitlab.com.", "https://gitlab.com"),
      text(
        "projectId",
        "Project",
        "Numeric id, or the URL-encoded path (group%2Fproject).",
        "12345",
        true,
      ),
      secret(
        "token",
        "Personal access token",
        "Needs read_api. Stored in the OS keychain, never in the workspace.",
      ),
    ],
    probeLabel: "The instance answered and the token was accepted.",
    operations: [
      {
        id: "pipelines",
        label: "Pipelines",
        summary: "The most recent pipelines on this project, newest first.",
        columns: ["Pipeline", "Ref", "Status", "Updated"],
        unit: "pipelines",
      },
      {
        id: "merge-requests",
        label: "Merge requests",
        summary: "Open merge requests awaiting review or merge.",
        columns: ["MR", "Title", "Author", "State"],
        unit: "merge requests",
      },
      {
        id: "issues",
        label: "Issues",
        summary: "Open issues on this project.",
        columns: ["Issue", "Title", "Assignee", "State"],
        unit: "issues",
      },
    ],
    docsUrl: "https://docs.gitlab.com/ee/api/rest/",
    phases: ["build", "review", "release"],
  },
  {
    id: "github",
    name: "GitHub",
    category: "source",
    blurb: "Pull requests, workflow runs and issues for one repository.",
    hue: "#8b7fd4",
    auth: "token",
    transport: "http",
    fields: [
      url("baseUrl", "API URL", "github.com, or your Enterprise API root.", "https://api.github.com"),
      text("repo", "Repository", "owner/name.", "octocat/hello-world", true),
      secret("token", "Personal access token", "Needs repo read scope."),
    ],
    probeLabel: "The API answered and the token identified a user.",
    operations: [
      {
        id: "pull-requests",
        label: "Pull requests",
        summary: "Open pull requests on this repository.",
        columns: ["PR", "Title", "Author", "State"],
        unit: "pull requests",
      },
      {
        id: "workflow-runs",
        label: "Workflow runs",
        summary: "Recent Actions runs, newest first.",
        columns: ["Run", "Workflow", "Conclusion", "Updated"],
        unit: "runs",
      },
      {
        id: "issues",
        label: "Issues",
        summary: "Open issues, excluding pull requests.",
        columns: ["Issue", "Title", "Assignee", "State"],
        unit: "issues",
      },
    ],
    docsUrl: "https://docs.github.com/rest",
    phases: ["build", "review", "release"],
  },

  // ——— planning ———
  {
    id: "jira",
    name: "Jira",
    category: "planning",
    blurb: "Issues, boards and the work your team has actually committed to.",
    hue: "#3d7de0",
    auth: "basic",
    transport: "http",
    fields: [
      url("baseUrl", "Site URL", "Your Atlassian site.", "https://acme.atlassian.net"),
      text("email", "Account email", "The account the API token belongs to.", "you@acme.com", true),
      text(
        "jql",
        "Default JQL",
        "The query the Issues read runs. Left empty, it uses assignee = currentUser().",
        "project = ENG AND statusCategory != Done",
      ),
      secret("token", "API token", "Create one at id.atlassian.com."),
    ],
    probeLabel: "The site answered and named the authenticated account.",
    operations: [
      {
        id: "issues",
        label: "Issues",
        summary: "Issues matching the configured JQL.",
        columns: ["Key", "Summary", "Assignee", "Status"],
        unit: "issues",
      },
      {
        id: "projects",
        label: "Projects",
        summary: "Projects this account can see.",
        columns: ["Key", "Name", "Type", "Lead"],
        unit: "projects",
      },
    ],
    docsUrl: "https://developer.atlassian.com/cloud/jira/platform/rest/v3/",
    phases: ["intake", "plan", "review"],
  },

  // ——— pipelines ———
  {
    id: "jenkins",
    name: "Jenkins",
    category: "pipeline",
    blurb: "Jobs and their last build result, straight from the controller.",
    hue: "#c9563f",
    auth: "basic",
    transport: "http",
    fields: [
      url("baseUrl", "Controller URL", "The Jenkins root.", "https://jenkins.acme.com"),
      text("user", "User", "The account the API token belongs to.", "build-bot", true),
      secret("token", "API token", "From the user's configure page."),
    ],
    probeLabel: "The controller answered and the token was accepted.",
    operations: [
      {
        id: "jobs",
        label: "Jobs",
        summary: "Top-level jobs and the colour the controller reports.",
        columns: ["Job", "Last build", "Result", "Health"],
        unit: "jobs",
      },
    ],
    docsUrl: "https://www.jenkins.io/doc/book/using/remote-access-api/",
    phases: ["build", "verify", "release"],
  },

  // ——— quality ———
  {
    id: "sonarqube",
    name: "SonarQube",
    category: "quality",
    blurb: "The quality gate and the issues standing behind it.",
    hue: "#3aa6c9",
    auth: "token",
    transport: "http",
    fields: [
      url("baseUrl", "Server URL", "SonarQube or SonarCloud.", "https://sonarcloud.io"),
      text("projectKey", "Project key", "As shown in the project settings.", "acme_service", true),
      secret("token", "User token", "Needs Browse permission on the project."),
    ],
    probeLabel: "The server answered and reported its own status as UP.",
    operations: [
      {
        id: "quality-gate",
        label: "Quality gate",
        summary: "The gate's status and each failing condition.",
        columns: ["Condition", "Actual", "Threshold", "Status"],
        unit: "conditions",
      },
      {
        id: "issues",
        label: "Issues",
        summary: "Open issues on this project, worst severity first.",
        columns: ["Rule", "File", "Severity", "Type"],
        unit: "issues",
      },
    ],
    docsUrl: "https://docs.sonarsource.com/sonarqube/latest/web-api/",
    phases: ["verify", "review", "security"],
  },

  // ——— API tooling ———
  {
    id: "postman",
    name: "Postman",
    category: "api",
    blurb: "Collections, environments and monitor results for your workspace.",
    hue: "#e07a35",
    auth: "token",
    transport: "http",
    fields: [
      secret("apiKey", "API key", "From Postman → Account Settings → API keys."),
    ],
    probeLabel: "Postman answered and the key identified an account.",
    operations: [
      {
        id: "collections",
        label: "Collections",
        summary: "Collections visible to this key.",
        columns: ["Collection", "Owner", "Updated", "Fork"],
        unit: "collections",
      },
      {
        id: "monitors",
        label: "Monitors",
        summary: "Monitors and their last run result.",
        columns: ["Monitor", "Collection", "Last run", "Result"],
        unit: "monitors",
      },
    ],
    docsUrl: "https://learning.postman.com/docs/developer/postman-api/intro-api/",
    phases: ["verify"],
  },

  // ——— runtimes ———
  {
    id: "docker",
    name: "Docker",
    category: "runtime",
    blurb: "Containers and images on the daemon this machine talks to.",
    hue: "#3d8fe0",
    auth: "cli-context",
    transport: "cli",
    binary: "docker",
    fields: [
      text(
        "context",
        "Context",
        "Leave empty to use the current docker context.",
        "default",
      ),
    ],
    probeLabel: "The docker CLI answered and a daemon reported its version.",
    operations: [
      {
        id: "containers",
        label: "Containers",
        summary: "Running containers, with image and uptime.",
        columns: ["Name", "Image", "Status", "Ports"],
        unit: "containers",
      },
      {
        id: "images",
        label: "Images",
        summary: "Local images and their size.",
        columns: ["Repository", "Tag", "Size", "Created"],
        unit: "images",
      },
    ],
    docsUrl: "https://docs.docker.com/reference/cli/docker/",
    phases: ["build", "verify", "release", "operate"],
  },
  {
    id: "kubernetes",
    name: "Kubernetes",
    category: "runtime",
    blurb: "Pods, deployments, nodes and recent events in one namespace.",
    hue: "#4a7de0",
    auth: "cli-context",
    transport: "cli",
    binary: "kubectl",
    fields: [
      text("context", "Context", "Leave empty to use the current kubeconfig context.", "prod"),
      text("namespace", "Namespace", "Leave empty for the context's default.", "default"),
    ],
    probeLabel: "kubectl reached the API server and it reported its version.",
    operations: [
      {
        id: "pods",
        label: "Pods",
        summary: "Pods in the namespace, with restarts and phase.",
        columns: ["Pod", "Ready", "Phase", "Restarts"],
        unit: "pods",
      },
      {
        id: "deployments",
        label: "Deployments",
        summary: "Deployments and how many replicas are actually ready.",
        columns: ["Deployment", "Ready", "Up to date", "Available"],
        unit: "deployments",
      },
      {
        id: "events",
        label: "Events",
        summary: "Recent events, warnings first.",
        columns: ["Object", "Reason", "Message", "Type"],
        unit: "events",
      },
      {
        id: "nodes",
        label: "Nodes",
        summary: "Cluster nodes and their Ready condition.",
        columns: ["Node", "Status", "Version", "Roles"],
        unit: "nodes",
      },
    ],
    docsUrl: "https://kubernetes.io/docs/reference/kubectl/",
    phases: ["release", "operate"],
  },
  {
    id: "openshift",
    name: "OpenShift",
    category: "runtime",
    blurb: "Projects, pods, routes and builds through the oc CLI.",
    hue: "#d0453d",
    auth: "cli-context",
    transport: "cli",
    binary: "oc",
    fields: [
      text("project", "Project", "Leave empty to use the current project.", "acme-prod"),
    ],
    probeLabel: "oc reached the cluster and named the logged-in user.",
    operations: [
      {
        id: "pods",
        label: "Pods",
        summary: "Pods in the project, with phase and restarts.",
        columns: ["Pod", "Ready", "Phase", "Restarts"],
        unit: "pods",
      },
      {
        id: "routes",
        label: "Routes",
        summary: "Exposed routes and the service behind each.",
        columns: ["Route", "Host", "Service", "Port"],
        unit: "routes",
      },
      {
        id: "builds",
        label: "Builds",
        summary: "Recent builds and their phase.",
        columns: ["Build", "Strategy", "Phase", "Started"],
        unit: "builds",
      },
    ],
    docsUrl: "https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html",
    phases: ["release", "operate"],
  },

  // ——— messaging & streaming ———
  {
    id: "kafka",
    name: "Kafka",
    category: "messaging",
    blurb: "Topics and consumer groups on the bootstrap servers you name.",
    hue: "#6b7ae0",
    auth: "cli-context",
    transport: "cli",
    binary: "kafka-topics.sh",
    fields: [
      text(
        "bootstrap",
        "Bootstrap servers",
        "Comma-separated host:port list.",
        "localhost:9092",
        true,
      ),
      text(
        "binDir",
        "Kafka bin directory",
        "Leave empty if the Kafka scripts are already on PATH.",
        "/opt/kafka/bin",
      ),
      text(
        "commandConfig",
        "Command config file",
        "Optional properties file for SASL or TLS.",
        "/etc/kafka/client.properties",
      ),
    ],
    probeLabel: "The Kafka CLI reached the bootstrap servers and listed topics.",
    operations: [
      {
        id: "topics",
        label: "Topics",
        summary: "Topics visible to this client.",
        columns: ["Topic"],
        unit: "topics",
      },
      {
        id: "consumer-groups",
        label: "Consumer groups",
        summary: "Consumer groups known to the cluster.",
        columns: ["Group"],
        unit: "consumer groups",
      },
    ],
    docsUrl: "https://kafka.apache.org/documentation/#basic_ops",
    phases: ["operate"],
  },
  {
    id: "slack",
    name: "Slack",
    category: "messaging",
    blurb: "Which workspace and channels Meridian can see. Read-only.",
    hue: "#3aa88b",
    auth: "token",
    transport: "http",
    fields: [
      secret(
        "token",
        "Bot or user token",
        "Needs channels:read. Meridian never posts — this connection cannot write.",
      ),
    ],
    probeLabel: "Slack accepted the token and named the workspace and user.",
    operations: [
      {
        id: "channels",
        label: "Channels",
        summary: "Public channels the token can see.",
        columns: ["Channel", "Members", "Purpose", "Archived"],
        unit: "channels",
      },
    ],
    docsUrl: "https://api.slack.com/web",
    phases: ["operate"],
  },

  // ——— observability ———
  {
    id: "datadog",
    name: "Datadog",
    category: "observability",
    blurb: "Monitors, their state, and what is currently alerting.",
    hue: "#8b5fd4",
    auth: "key-pair",
    transport: "http",
    fields: [
      text("site", "Site", "datadoghq.com, datadoghq.eu, ddog-gov.com …", "datadoghq.com", true),
      secret("apiKey", "API key", "Organisation API key."),
      secret("appKey", "Application key", "Needed for anything beyond validation."),
    ],
    probeLabel: "Datadog validated the API key for this site.",
    operations: [
      {
        id: "monitors",
        label: "Monitors",
        summary: "Monitors and their current overall state.",
        columns: ["Monitor", "Type", "State", "Tags"],
        unit: "monitors",
      },
      {
        id: "alerting",
        label: "Alerting now",
        summary: "Only the monitors currently in Alert or Warn.",
        columns: ["Monitor", "Type", "State", "Tags"],
        unit: "alerting monitors",
      },
    ],
    docsUrl: "https://docs.datadoghq.com/api/latest/",
    phases: ["operate"],
  },
  {
    id: "grafana",
    name: "Grafana",
    category: "observability",
    blurb: "Dashboards, data sources and provisioned alert rules.",
    hue: "#e08a30",
    auth: "token",
    transport: "http",
    fields: [
      url("baseUrl", "Grafana URL", "Your Grafana root.", "https://grafana.acme.com"),
      secret("token", "Service account token", "Needs Viewer at minimum."),
    ],
    probeLabel: "Grafana answered its health endpoint and reported a version.",
    operations: [
      {
        id: "dashboards",
        label: "Dashboards",
        summary: "Dashboards this token can see.",
        columns: ["Dashboard", "Folder", "Type", "Tags"],
        unit: "dashboards",
      },
      {
        id: "datasources",
        label: "Data sources",
        summary: "Configured data sources and their type.",
        columns: ["Name", "Type", "URL", "Default"],
        unit: "data sources",
      },
      {
        id: "alert-rules",
        label: "Alert rules",
        summary: "Provisioned alert rules and the folder they live in.",
        columns: ["Rule", "Folder", "Group", "For"],
        unit: "alert rules",
      },
    ],
    docsUrl: "https://grafana.com/docs/grafana/latest/developers/http_api/",
    phases: ["verify", "operate"],
  },
  {
    id: "kibana",
    name: "Kibana",
    category: "observability",
    blurb: "Kibana's own status, its spaces and its data views.",
    hue: "#d44f7a",
    auth: "basic",
    transport: "http",
    fields: [
      url("baseUrl", "Kibana URL", "Your Kibana root.", "https://kibana.acme.com"),
      text("user", "User", "Leave empty when using an API key.", "elastic"),
      secret(
        "password",
        "Password or API key",
        "A password when a user is set; otherwise an encoded API key.",
      ),
    ],
    probeLabel: "Kibana answered its status endpoint and reported overall state.",
    operations: [
      {
        id: "status",
        label: "Status",
        summary: "Each Kibana core service and its reported level.",
        columns: ["Service", "Level", "Summary", "Since"],
        unit: "services",
      },
      {
        id: "data-views",
        label: "Data views",
        summary: "Saved data views this account can see.",
        columns: ["Data view", "Title", "Time field", "Id"],
        unit: "data views",
      },
      {
        id: "spaces",
        label: "Spaces",
        summary: "Kibana spaces and their descriptions.",
        columns: ["Space", "Id", "Description", "Disabled features"],
        unit: "spaces",
      },
    ],
    docsUrl: "https://www.elastic.co/guide/en/kibana/current/api.html",
    phases: ["operate"],
  },

  // ——— cloud ———
  {
    id: "aws",
    name: "AWS",
    category: "cloud",
    blurb: "Caller identity, buckets, instances and alarms through the AWS CLI.",
    hue: "#e0a232",
    auth: "cli-context",
    transport: "cli",
    binary: "aws",
    fields: [
      text("profile", "Profile", "Leave empty for the default profile.", "prod"),
      text("region", "Region", "Leave empty to use the profile's region.", "eu-west-1"),
    ],
    probeLabel: "The AWS CLI answered and STS named the calling identity.",
    operations: [
      {
        id: "identity",
        label: "Caller identity",
        summary: "Exactly which principal these credentials are.",
        columns: ["Field", "Value"],
        unit: "fields",
      },
      {
        id: "buckets",
        label: "S3 buckets",
        summary: "Buckets owned by this account.",
        columns: ["Bucket", "Created"],
        unit: "buckets",
      },
      {
        id: "instances",
        label: "EC2 instances",
        summary: "Instances in the region, with state and type.",
        columns: ["Instance", "Name", "State", "Type"],
        unit: "instances",
      },
      {
        id: "alarms",
        label: "CloudWatch alarms",
        summary: "Alarms and their current state.",
        columns: ["Alarm", "State", "Metric", "Updated"],
        unit: "alarms",
      },
    ],
    docsUrl: "https://docs.aws.amazon.com/cli/latest/reference/",
    phases: ["release", "operate"],
  },

  // ——— scheduling ———
  {
    id: "control-m",
    name: "Control-M",
    category: "scheduling",
    blurb: "Job status and servers through the Automation API.",
    hue: "#c96a3a",
    auth: "token",
    transport: "http",
    fields: [
      url(
        "baseUrl",
        "Automation API URL",
        "Including the /automation-api path.",
        "https://ctm.acme.com:8443/automation-api",
      ),
      text(
        "query",
        "Job filter",
        "Optional. Passed to the job status query, e.g. ctm=PROD or jobname=DAILY*.",
        "ctm=PROD",
      ),
      secret("token", "API token", "From `ctm session login`, or a service token."),
    ],
    probeLabel: "The Automation API answered and listed its configured servers.",
    operations: [
      {
        id: "jobs",
        label: "Job status",
        summary: "Jobs matching the filter, with their current status.",
        columns: ["Job", "Folder", "Status", "Host"],
        unit: "jobs",
      },
      {
        id: "servers",
        label: "Servers",
        summary: "Control-M/Servers this endpoint knows about.",
        columns: ["Server", "State", "Host", "Version"],
        unit: "servers",
      },
    ],
    docsUrl: "https://docs.bmc.com/docs/automation-api/",
    phases: ["release", "operate"],
  },

  // ——— browser ———
  {
    id: "chrome",
    name: "Chrome",
    category: "browser",
    blurb:
      "A Chrome started with remote debugging, so an agent can see the pages open in it.",
    hue: "#3ab07a",
    auth: "none",
    transport: "http",
    fields: [
      url(
        "baseUrl",
        "DevTools endpoint",
        "Start Chrome with --remote-debugging-port=9222.",
        "http://127.0.0.1:9222",
      ),
    ],
    probeLabel: "Chrome answered on the DevTools port and reported its version.",
    operations: [
      {
        id: "targets",
        label: "Open targets",
        summary: "Tabs, workers and frames currently open.",
        columns: ["Title", "Type", "URL", "Id"],
        unit: "targets",
      },
    ],
    docsUrl: "https://chromedevtools.github.io/devtools-protocol/",
    phases: ["verify"],
  },
];

export function integrationById(id: string): IntegrationDefinition | undefined {
  return INTEGRATIONS.find((entry) => entry.id === id);
}

export function integrationsByCategory(): {
  category: IntegrationCategory;
  label: string;
  items: IntegrationDefinition[];
}[] {
  const order = Object.keys(INTEGRATION_CATEGORY_LABELS) as IntegrationCategory[];
  return order
    .map((category) => ({
      category,
      label: INTEGRATION_CATEGORY_LABELS[category],
      items: INTEGRATIONS.filter((entry) => entry.category === category),
    }))
    .filter((group) => group.items.length > 0);
}

// ——— stored connections ———————————————————————————————————————————————

export interface IntegrationProbeResult {
  ok: boolean;
  /** ISO timestamp of the attempt, so a stale green is visibly stale. */
  at: string;
  /** What actually came back, in a sentence. Never "success"/"failure". */
  detail: string;
  latencyMs: number;
  /** HTTP status or process exit code, so a failure is diagnosable. */
  code?: number;
}

export interface IntegrationConnectionInput {
  id: string;
  integrationId: string;
  name: string;
  /** Non-secret fields only. Secrets travel separately and one way. */
  config: Record<string, string>;
  /**
   * Write-only. Present on save, stored in the OS keychain, and never
   * returned in a snapshot — not even redacted, because a redacted secret
   * still tells you its length.
   */
  secrets?: Record<string, string>;
}

export interface IntegrationConnection
  extends Omit<IntegrationConnectionInput, "secrets"> {
  enabled: boolean;
  /** Which secret fields have a stored value. Names only, never values. */
  secretKeys: string[];
  lastProbe?: IntegrationProbeResult;
  createdAt: string;
  updatedAt: string;
}

export type IntegrationRowState = "ok" | "warn" | "fail" | "idle";

export interface IntegrationRow {
  id: string;
  cells: string[];
  state: IntegrationRowState;
  /** Where this row lives in the connected system, when it has an address. */
  href?: string;
}

export interface IntegrationReadResult {
  connectionId: string;
  operationId: string;
  at: string;
  columns: string[];
  rows: IntegrationRow[];
  /** A sentence naming what was fetched and from where. */
  detail: string;
  /** True when the system had more than the read limit. */
  truncated: boolean;
  latencyMs: number;
}

/** The most rows one read will return, so a big estate cannot flood the panel. */
export const INTEGRATION_READ_LIMIT = 100;
