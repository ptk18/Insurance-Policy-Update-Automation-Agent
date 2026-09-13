export type Changes = Partial<
  Record<"mailing_address" | "email" | "phone", string>
>;
export type CaseStatus =
  | "received"
  | "processing"
  | "awaiting_information"
  | "awaiting_approval"
  | "approved"
  | "completed"
  | "rejected"
  | "blocked";
export type Intake = {
  broker_id: string;
  original_request: string;
  policy_number?: string;
  changes?: Changes;
  evidence_id?: string;
};
export type Evidence = {
  name: string;
  address: string;
  readable: boolean;
  certain: boolean;
  reason?: string;
  source?: {
    kind: string;
    id: string;
    filename?: string;
    page?: number;
    pages?: number;
  };
};
export type Attachment = {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  inspection: Evidence;
};
export type Proposal = {
  id: string;
  version: number;
  changes: Changes;
  before: Record<string, string>;
  findings: { code: string; message: string }[];
  evidence: Evidence | null;
  status: string;
  approved_at: string | null;
  policy_revision: number | null;
};
export type CaseSummary = {
  id: string;
  status: CaseStatus;
  job_status: string | null;
  policy_number: string | null;
  broker_id: string;
  created_at: string;
};
export type Case = CaseSummary & {
  original_request: string;
  replies: { text: string; created_at: string }[];
  attachments: Attachment[];
  evidence_id: string | null;
  requested_changes: Changes | null;
  current_version: number;
  proposals: Proposal[];
  follow_up_draft: string | null;
  confirmation_draft: string | null;
  job: {
    status: string;
    action: string;
    attempts: number;
    retryable: boolean;
    last_error: string | null;
  } | null;
  timeline: {
    id: number;
    actor: string;
    action: string;
    proposal_version: number | null;
    details: Record<string, unknown>;
    created_at: string;
  }[];
};
export type Fixtures = {
  brokers: { id: string; name: string; policy_numbers: string[] }[];
  evidence: Record<string, Evidence>;
  samples: { title: string; intake: Intake }[];
  documents: {
    id: string;
    title: string;
    filename: string;
    content_type: string;
    download: string;
  }[];
};
export type Health = {
  status: string;
  extraction: string;
  agent: string;
  worker: string;
};
export const fields = {
  mailing_address: "Mailing address",
  email: "Email address",
  phone: "Phone number",
} as const;
export const statuses: Record<CaseStatus, { label: string; tone: string }> = {
  received: { label: "Received", tone: "neutral" },
  processing: { label: "Processing", tone: "info" },
  awaiting_information: { label: "Needs information", tone: "warning" },
  awaiting_approval: { label: "Ready for review", tone: "info" },
  approved: { label: "Approved · update pending", tone: "warning" },
  completed: { label: "Completed", tone: "success" },
  rejected: { label: "Rejected", tone: "neutral" },
  blocked: { label: "Access blocked", tone: "danger" },
};
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch(`/api/${path}`, {
    method,
    cache: "no-store",
    headers: body && !form ? { "Content-Type": "application/json" } : {},
    body: body ? (form ? body : JSON.stringify(body)) : undefined,
  });
  const data = await response.json();
  if (!response.ok) {
    const message =
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((e: { msg: string }) => e.msg).join(". ")
          : "Something went wrong. Please try again.";
    throw new ApiError(response.status, message);
  }
  return data;
}
