"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronRight,
  Clock3,
  FileCheck2,
  FileText,
  ListFilter,
  LoaderCircle,
  Mail,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import {
  api,
  ApiError,
  fields,
  statuses,
  type Case,
  type CaseStatus,
  type CaseSummary,
  type Fixtures,
  type Health,
  type Proposal,
} from "@/lib/types";
import { Badge, date, Dialog, Notice, SupportNote } from "./primitives";
import { IntakeDialog, ReviewDialog } from "./forms";

type Modal = "intake" | "edit" | "reject" | "reply" | "samples" | "help" | null;
type Filter = "all" | CaseStatus;
const attention: CaseStatus[] = [
  "awaiting_information",
  "awaiting_approval",
  "approved",
];

export default function Dashboard() {
  const [connected, setConnected] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [fixtures, setFixtures] = useState<Fixtures | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [record, setRecord] = useState<Case | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const selectedRef = useRef<string | null>(null);
  const requestEpoch = useRef(0);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [stale, setStale] = useState(false);
  const [modal, setModal] = useState<Modal>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState("review");
  const markBusy = (value: boolean) => {
    busyRef.current = value;
    setBusy(value);
  };
  const fail = useCallback((value: unknown) => {
    setError(
      value instanceof Error
        ? value.message
        : "The request could not be completed.",
    );
    if (value instanceof ApiError) {
      if ([401, 403, 404].includes(value.status)) {
        setRecord(null);
        setModal(null);
        requestEpoch.current++;
      }
      if (value.status === 401) {
        selectedRef.current = null;
        setSelected(null);
        setConnected(false);
        setCases([]);
        setFixtures(null);
      }
      if (value.status === 409) setStale(true);
    }
  }, []);
  const refresh = useCallback(
    async (manual = false) => {
      const epoch = ++requestEpoch.current;
      const id = selectedRef.current;
      try {
        const [rows, current] = await Promise.all([
          api<CaseSummary[]>("backend/cases"),
          id ? api<Case>(`backend/cases/${id}`) : Promise.resolve(null),
        ]);
        if (epoch !== requestEpoch.current) return;
        setCases(rows);
        setRecord(current);
        if (manual) {
          setError("");
          setStale(false);
          setNotice(
            "Case refreshed. Review the current version before acting.",
          );
        }
      } catch (e) {
        if (epoch === requestEpoch.current) fail(e);
      } finally {
        if (epoch === requestEpoch.current) setLoading(false);
      }
    },
    [fail],
  );
  const load = useCallback(async () => {
    const [data, service] = await Promise.all([
      api<Fixtures>("backend/fixtures"),
      api<Health>("backend/health"),
    ]);
    setFixtures(data);
    setHealth(service);
    setConnected(true);
    await refresh();
  }, [refresh]);
  useEffect(() => {
    api<{ connected: boolean }>("session")
      .then((session) => {
        if (session.connected) return load();
      })
      .catch(fail)
      .finally(() => setInitializing(false));
  }, [load, fail]);
  useEffect(() => {
    if (!connected) return;
    const timer = setInterval(() => {
      if (!busyRef.current && document.visibilityState === "visible")
        void refresh();
    }, 2000);
    return () => clearInterval(timer);
  }, [connected, refresh]);
  function select(id: string) {
    selectedRef.current = id;
    setSelected(id);
    setRecord(null);
    setLoading(true);
    setError("");
    setNotice("");
    setStale(false);
    setTab("review");
    void refresh();
  }
  async function connect() {
    markBusy(true);
    setError("");
    try {
      await api("session", "POST");
      await load();
    } catch (e) {
      fail(e);
    } finally {
      markBusy(false);
    }
  }
  async function resetSession() {
    markBusy(true);
    try {
      await api("session", "DELETE");
      requestEpoch.current++;
      selectedRef.current = null;
      setSelected(null);
      setRecord(null);
      setCases([]);
      setError("");
    } catch (e) {
      fail(e);
    } finally {
      markBusy(false);
    }
  }
  function changed(value: Case, message: string) {
    requestEpoch.current++;
    setRecord(value);
    setNotice(message);
    setError("");
    setStale(false);
    void refresh();
  }
  async function action(name: string) {
    if (!record) return;
    const snapshot = record;
    requestEpoch.current++;
    markBusy(true);
    setError("");
    setNotice("");
    try {
      await api(
        `backend/cases/${snapshot.id}/${name}`,
        "POST",
        ["approve", "execute"].includes(name)
          ? { version: snapshot.current_version }
          : undefined,
      );
      await refresh();
      setNotice(
        name === "approve"
          ? `Version ${snapshot.current_version} approved. Apply the update when ready.`
          : name === "execute"
            ? "The approved update was applied."
            : "Your request is queued. Progress will appear here automatically.",
      );
    } catch (e) {
      fail(e);
    } finally {
      markBusy(false);
    }
  }
  const proposal = record?.proposals.at(-1);
  const activeJob =
    record?.job && ["queued", "running"].includes(record.job.status);
  const editable =
    record &&
    !activeJob &&
    ["awaiting_approval", "awaiting_information", "approved"].includes(
      record.status,
    );
  const disabled = busy || stale || Boolean(activeJob);
  const filtered = cases.filter(
    (c) =>
      (filter === "all" || c.status === filter) &&
      `${c.policy_number || ""} ${c.id} ${fixtures?.brokers.find((b) => b.id === c.broker_id)?.name}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to workspace
      </a>
      <div className="workspace">
        <header className="topbar">
          <a className="brand" href="/" aria-label="Policy desk home">
            Policy desk <span className="demo-tag">Demo</span>
          </a>
          <nav className="topbar-actions" aria-label="Main navigation">
            <button
              className="button quiet"
              disabled={!fixtures}
              onClick={(event) => {
                event.currentTarget.focus();
                setModal("samples");
              }}
            >
              Sample library
            </button>
            <button
              className="button quiet"
              onClick={(event) => {
                event.currentTarget.focus();
                setModal("help");
              }}
            >
              Help
            </button>
          </nav>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <h1>Policy requests</h1>
              <p>
                Manage mailing address, email, and phone updates in one place.
              </p>
            </div>
            {connected && (
              <button
                className="button primary"
                onClick={(event) => {
                  event.currentTarget.focus();
                  setModal("intake");
                }}
                disabled={!fixtures || busy}
              >
                <Plus size={17} />
                New request
              </button>
            )}
          </div>
          {error && (
            <Notice>
              {error}
              {stale && (
                <p>
                  Refresh, compare the latest proposal, and review again. Your
                  previous action was not accepted.
                </p>
              )}
              {connected && (
                <button
                  className="text-button"
                  onClick={() => void refresh(true)}
                >
                  Refresh workspace
                </button>
              )}
              {!connected && (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={resetSession}
                >
                  Clear expired session
                </button>
              )}
            </Notice>
          )}
          {notice && (
            <div className="feedback" role="status">
              <CheckCircle2Icon />
              {notice}
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                ×
              </button>
            </div>
          )}
          {initializing ? (
            <div className="empty-state">
              <LoaderCircle className="spin" />
              <h2>Opening your workspace…</h2>
            </div>
          ) : !connected ? (
            <section className="welcome">
              <h2>Open a review workspace</h2>
              <p>
                Try a request, review the details, and approve the update. This
                demo uses fictional records. No sign-up needed.
              </p>
              <button
                className="button primary"
                onClick={connect}
                disabled={busy}
              >
                {busy ? "Opening workspace…" : "Open demo workspace"}
              </button>
            </section>
          ) : (
            <>
              <div className="queue-toolbar">
                <div>
                  <h2>
                    Your requests <span className="count">{cases.length}</span>
                  </h2>
                </div>
                <div className="queue-controls">
                  <label className="search">
                    <Search size={16} />
                    <input
                      aria-label="Search requests"
                      placeholder="Search policy or broker…"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </label>
                  <label className="filter">
                    <ListFilter size={16} />
                    <select
                      aria-label="Filter by status"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value as Filter)}
                    >
                      <option value="all">All statuses</option>
                      {Object.entries(statuses).map(([value, state]) => (
                        <option key={value} value={value}>
                          {state.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="icon-button"
                    aria-label="Refresh cases"
                    disabled={busy}
                    onClick={() => void refresh(true)}
                  >
                    <RefreshCw size={17} />
                  </button>
                </div>
              </div>
              {!cases.length ? (
                <section className="empty-state first-case">
                  <h2>No requests yet</h2>
                  <p>
                    Start with a broker email or try a sample. We’ll help
                    prepare the changes for review.
                  </p>
                  <button
                    className="button primary"
                    onClick={(event) => {
                      event.currentTarget.focus();
                      setModal("intake");
                    }}
                  >
                    <Plus size={17} />
                    Create request
                  </button>
                  <button
                    className="text-button"
                    onClick={(event) => {
                      event.currentTarget.focus();
                      setModal("samples");
                    }}
                  >
                    Browse sample documents <ArrowRight size={15} />
                  </button>
                </section>
              ) : (
                <div
                  className={`queue-layout ${selected ? "has-selection" : ""}`}
                >
                  <section className="case-list" aria-label="Requests">
                    <div className="list-heading">
                      {filtered.length} request
                      {filtered.length === 1 ? "" : "s"}
                      <span>Newest first</span>
                    </div>
                    {!filtered.length && (
                      <div className="list-empty">
                        No requests match these filters.
                        <button
                          className="text-button"
                          onClick={() => {
                            setSearch("");
                            setFilter("all");
                          }}
                        >
                          Clear filters
                        </button>
                      </div>
                    )}
                    {filtered.map((c) => (
                      <button
                        className={`case-row ${selected === c.id ? "selected" : ""}`}
                        key={c.id}
                        onClick={() => select(c.id)}
                        aria-pressed={selected === c.id}
                      >
                        <div className="case-row-top">
                          <span
                            className={`case-icon ${attention.includes(c.status) ? "attention" : ""}`}
                          >
                            <FileText size={19} />
                          </span>
                          <span className="case-reference">
                            {c.policy_number || "Policy to confirm"}
                            <small>Request {c.id.slice(0, 8)}</small>
                          </span>
                          <ChevronRight size={16} />
                        </div>
                        <Badge status={c.status} />
                        <div className="case-row-bottom">
                          <span>
                            {fixtures?.brokers.find((b) => b.id === c.broker_id)
                              ?.name || "Broker"}
                          </span>
                          <time>{date(c.created_at)}</time>
                        </div>
                        {c.job_status === "failed" && (
                          <span className="row-error">
                            Needs attention · view details
                          </span>
                        )}
                        {["queued", "running"].includes(c.job_status || "") && (
                          <span className="row-progress">
                            <LoaderCircle size={12} className="spin" />
                            {c.job_status === "queued"
                              ? "Waiting to start"
                              : "Preparing changes…"}
                          </span>
                        )}
                      </button>
                    ))}
                  </section>
                  <section
                    className="case-detail"
                    aria-label="Selected request"
                    aria-busy={loading}
                  >
                    {loading ? (
                      <div className="empty-state">
                        <LoaderCircle className="spin" />
                        <p>Loading request…</p>
                      </div>
                    ) : !record ? (
                      <div className="empty-state">
                        <h2>Select a request</h2>
                        <p>
                          Select a request to review its changes and supporting
                          evidence.
                        </p>
                      </div>
                    ) : (
                      <>
                        <div className="detail-heading">
                          <div className="detail-title">
                            <span className="eyebrow">
                              Request {record.id.slice(0, 8)}
                            </span>
                            <h2>
                              {record.policy_number || "Policy to confirm"}
                            </h2>
                            <p>
                              {
                                fixtures?.brokers.find(
                                  (b) => b.id === record.broker_id,
                                )?.name
                              }{" "}
                              <span>·</span> {date(record.created_at)}
                            </p>
                          </div>
                          <Badge status={record.status} />
                        </div>
                        <div
                          className="tabs"
                          role="tablist"
                          aria-label="Case sections"
                        >
                          {[
                            ["review", "Review"],
                            ["evidence", "Request & evidence"],
                            ["activity", "Activity"],
                          ].map(([value, label], index) => (
                            <button
                              key={value}
                              id={`tab-${value}`}
                              role="tab"
                              aria-selected={tab === value}
                              aria-controls="case-panel"
                              tabIndex={tab === value ? 0 : -1}
                              className={tab === value ? "active" : ""}
                              onClick={() => setTab(value)}
                              onKeyDown={(e) => {
                                if (
                                  [
                                    "ArrowRight",
                                    "ArrowLeft",
                                    "Home",
                                    "End",
                                  ].includes(e.key)
                                ) {
                                  e.preventDefault();
                                  const tabs = [
                                    "review",
                                    "evidence",
                                    "activity",
                                  ];
                                  const next =
                                    e.key === "Home"
                                      ? 0
                                      : e.key === "End"
                                        ? 2
                                        : (index +
                                            (e.key === "ArrowRight" ? 1 : 2)) %
                                          3;
                                  setTab(tabs[next]);
                                  document
                                    .getElementById(`tab-${tabs[next]}`)
                                    ?.focus();
                                }
                              }}
                            >
                              {label}
                              {value === "activity" && (
                                <span>{record.timeline.length}</span>
                              )}
                            </button>
                          ))}
                        </div>
                        <div
                          className="detail-body"
                          role="tabpanel"
                          id="case-panel"
                          aria-labelledby={`tab-${tab}`}
                        >
                          {record.job?.status === "failed" && (
                            <Notice>
                              <strong>Processing needs attention</strong>
                              <p>
                                {record.job.last_error ||
                                  "The last attempt did not finish."}
                              </p>
                              <p>
                                Attempt {record.job.attempts}.{" "}
                                {record.job.retryable
                                  ? "You can retry when the service is available."
                                  : "Resolve the reported issue before retrying."}
                              </p>
                              <button
                                className="button secondary small"
                                disabled={busy}
                                onClick={() => void action("retry")}
                              >
                                <RefreshCw size={14} />
                                Retry processing
                              </button>
                            </Notice>
                          )}
                          {activeJob && (
                            <div className="processing-banner" role="status">
                              <LoaderCircle size={18} className="spin" />
                              <div>
                                <strong>
                                  {record.job?.status === "queued"
                                    ? "Waiting to start"
                                    : "Preparing this request"}
                                </strong>
                                <p>
                                  Progress is saved automatically. You can leave
                                  and return.
                                </p>
                              </div>
                            </div>
                          )}
                          {tab === "review" && (
                            <>
                              {record.status === "received" &&
                                !activeJob &&
                                record.job?.status !== "failed" && (
                                  <Notice tone="info">
                                    The request is saved and ready to process.
                                    <p>
                                      <button
                                        className="button primary small"
                                        disabled={busy}
                                        onClick={() => void action("process")}
                                      >
                                        Start processing
                                      </button>
                                    </p>
                                  </Notice>
                                )}
                              {record.status === "blocked" && (
                                <Notice>
                                  Broker access could not be verified. Policy
                                  values are unavailable and no update can be
                                  approved.
                                </Notice>
                              )}
                              {proposal && (
                                <ReviewSummary
                                  record={record}
                                  proposal={proposal}
                                  edit={
                                    editable
                                      ? () => setModal("edit")
                                      : undefined
                                  }
                                  disabled={disabled}
                                />
                              )}
                              {!proposal && record.status !== "blocked" && (
                                <div className="section-block">
                                  <h3>Original request</h3>
                                  <p className="request-text">
                                    {record.original_request}
                                  </p>
                                  <p className="muted">
                                    The proposed changes will appear after
                                    processing.
                                  </p>
                                </div>
                              )}
                              {record.follow_up_draft && (
                                <Draft
                                  title="Follow-up draft"
                                  text={record.follow_up_draft}
                                />
                              )}
                              {record.confirmation_draft && (
                                <Draft
                                  title="Confirmation draft"
                                  text={record.confirmation_draft}
                                />
                              )}
                              {record.status === "completed" && (
                                <Notice tone="success">
                                  The policy has been updated. View Activity for
                                  the record of this update (version{" "}
                                  {record.current_version}).
                                </Notice>
                              )}
                              {record.status === "rejected" && (
                                <Notice tone="info">
                                  This request is closed.{" "}
                                  {String(
                                    record.timeline.findLast(
                                      (e) => e.action === "proposal_rejected",
                                    )?.details.reason ||
                                      "No policy change was applied.",
                                  )}
                                </Notice>
                              )}
                            </>
                          )}
                          {tab === "evidence" && (
                            <>
                              <div className="section-block">
                                <div className="section-label">
                                  <Mail size={16} />
                                  Original email
                                </div>
                                <p className="request-text">
                                  {record.original_request}
                                </p>
                              </div>
                              {record.replies.map((reply, i) => (
                                <div className="section-block" key={i}>
                                  <div className="section-label">
                                    Reply {i + 1} · {date(reply.created_at)}
                                  </div>
                                  <p className="request-text">{reply.text}</p>
                                </div>
                              ))}
                              <EvidencePanel
                                record={record}
                                proposal={proposal}
                              />
                              <h3>
                                Attachments{" "}
                                <span className="count">
                                  {record.attachments.length}
                                </span>
                              </h3>
                              {record.attachments.length ? (
                                record.attachments.map((a) => (
                                  <div key={a.id} className="attachment">
                                    <FileText size={24} />
                                    <div>
                                      <strong>{a.filename}</strong>
                                      <small>
                                        {Math.ceil(a.size / 1024)} KB ·{" "}
                                        {a.inspection.certain
                                          ? "Document text checked"
                                          : "Needs verification"}
                                        {a.id === record.evidence_id
                                          ? " · Current evidence"
                                          : " · Not selected"}
                                      </small>
                                      {a.inspection.reason && (
                                        <p>{a.inspection.reason}</p>
                                      )}
                                    </div>
                                    <a
                                      className="icon-button"
                                      href={`/api/backend/cases/${record.id}/attachments/${a.id}/content`}
                                      download
                                      aria-label={`Download ${a.filename}`}
                                    >
                                      <ArrowDownToLine size={18} />
                                    </a>
                                  </div>
                                ))
                              ) : (
                                <p className="muted">
                                  No files uploaded. Any sample document used
                                  for this request appears above.
                                </p>
                              )}
                            </>
                          )}
                          {tab === "activity" && (
                            <>
                              <div className="section-label">
                                <Clock3 size={16} />
                                Request history
                              </div>
                              <ol className="timeline">
                                {record.timeline.toReversed().map((e) => (
                                  <li key={e.id}>
                                    <span className="timeline-marker">
                                      <Check size={12} />
                                    </span>
                                    <div>
                                      <strong>
                                        {e.action.replaceAll("_", " ")}
                                      </strong>
                                      <small>
                                        {e.actor.startsWith("reviewer:")
                                          ? "Guest reviewer"
                                          : e.actor}{" "}
                                        · {date(e.created_at)}
                                        {e.proposal_version
                                          ? ` · v${e.proposal_version}`
                                          : ""}
                                      </small>
                                      {Object.keys(e.details).length > 0 && (
                                        <details>
                                          <summary>View details</summary>
                                          <pre>
                                            {JSON.stringify(e.details, null, 2)}
                                          </pre>
                                        </details>
                                      )}
                                    </div>
                                  </li>
                                ))}
                              </ol>
                              <h3>Proposal history</h3>
                              {record.proposals.toReversed().map((p) => (
                                <details className="version" key={p.id}>
                                  <summary>
                                    Version {p.version}
                                    <span>{p.status}</span>
                                  </summary>
                                  <Comparison
                                    proposal={p}
                                    applied={p.status === "applied"}
                                  />
                                </details>
                              ))}
                            </>
                          )}
                        </div>
                        {editable && (
                          <footer className="review-actions">
                            <div>
                              <ShieldCheck size={18} />
                              <span>
                                {record.status === "approved"
                                  ? `Version ${record.current_version} approved. Update not yet applied.`
                                  : `Reviewing version ${record.current_version}`}
                                <small>
                                  {record.status === "awaiting_information"
                                    ? "Add the missing or corrected information to continue."
                                    : "Approval is for this version only."}
                                </small>
                              </span>
                            </div>
                            <div className="action-buttons">
                              <button
                                className="button quiet"
                                disabled={disabled}
                                onClick={(event) => {
                                  event.currentTarget.focus();
                                  setModal("reject");
                                }}
                              >
                                Reject
                              </button>
                              <button
                                className="button secondary"
                                disabled={disabled}
                                onClick={(event) => {
                                  event.currentTarget.focus();
                                  setModal("reply");
                                }}
                              >
                                Add information
                              </button>
                              {record.status === "awaiting_approval" && (
                                <button
                                  className="button primary"
                                  disabled={
                                    disabled ||
                                    Boolean(proposal?.findings.length)
                                  }
                                  onClick={() => void action("approve")}
                                >
                                  <Check size={16} />
                                  Approve v{record.current_version}
                                </button>
                              )}
                              {record.status === "approved" && (
                                <button
                                  className="button primary"
                                  disabled={disabled}
                                  onClick={() =>
                                    void action(
                                      health?.agent !== "unconfigured"
                                        ? "resume"
                                        : "execute",
                                    )
                                  }
                                >
                                  Apply approved update
                                  <ArrowRight size={16} />
                                </button>
                              )}
                              {record.status === "awaiting_information" &&
                                record.replies.length > 0 &&
                                health?.agent !== "unconfigured" && (
                                  <button
                                    className="button primary"
                                    disabled={disabled}
                                    onClick={() => void action("resume")}
                                  >
                                    Resume processing
                                  </button>
                                )}
                            </div>
                          </footer>
                        )}
                      </>
                    )}
                  </section>
                </div>
              )}
            </>
          )}
        </main>
      </div>
      {modal === "intake" && fixtures && (
        <IntakeDialog
          fixtures={fixtures}
          health={health}
          close={() => setModal(null)}
          saved={select}
        />
      )}
      {(["edit", "reject", "reply"] as const).includes(modal as "edit") &&
        record &&
        fixtures && (
          <ReviewDialog
            kind={modal as "edit" | "reject" | "reply"}
            record={record}
            fixtures={fixtures}
            close={() => setModal(null)}
            changed={changed}
            failed={fail}
          />
        )}
      {modal === "samples" && fixtures && (
        <Dialog title="Sample document library" close={() => setModal(null)}>
          <div className="dialog-body">
            <p className="muted">
              Download a sample document to try an address change. Each file
              uses fictional details; some examples intentionally need
              correction.
            </p>
            <SupportNote />
            {fixtures.documents.map((doc) => (
              <a
                className="sample-document"
                key={doc.id}
                href={`/api/backend/fixtures/documents/${doc.id}`}
                download
              >
                <FileText size={21} />
                <span>
                  <strong>{doc.title}</strong>
                  <small>{doc.filename}</small>
                </span>
                <ArrowDownToLine size={17} />
              </a>
            ))}
            <button
              className="button primary"
              onClick={(event) => {
                event.currentTarget.focus();
                setModal("intake");
              }}
            >
              Create a request
              <Plus size={17} />
            </button>
          </div>
        </Dialog>
      )}
      {modal === "help" && (
        <Dialog title="How to review a request" close={() => setModal(null)}>
          <div className="dialog-body">
            <ol className="help-steps">
              <li>
                <strong>Add an email.</strong> Paste the broker’s email or try a
                sample. Include the policy number and requested address, email,
                or phone changes. Attach proof of address for an address change.
              </li>
              <li>
                <strong>Review the changes.</strong> Compare the current and new
                details. If anything is missing or doesn’t match, add the
                corrected information and check again.
              </li>
              <li>
                <strong>Approve, then apply.</strong> Approve the version you’ve
                reviewed, then choose Apply approved update to save it. Any
                edits or replies need a new review and approval.
              </li>
            </ol>
            <SupportNote />
            <Notice tone="info">
              This is a demo with fictional policies and brokers. Email drafts
              are saved here; nothing is sent.
            </Notice>
            <button className="button primary" onClick={() => setModal(null)}>
              Got it
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function CheckCircle2Icon() {
  return <Check size={16} />;
}
function Draft({ title, text }: { title: string; text: string }) {
  return (
    <section className="draft">
      <div className="section-label">
        <Mail size={16} />
        {title}
        <span className="pill">Not sent</span>
      </div>
      <p className="request-text">{text}</p>
    </section>
  );
}
function Comparison({
  proposal,
  applied = false,
}: {
  proposal: Proposal;
  applied?: boolean;
}) {
  const entries = Object.entries(proposal.changes);
  if (!entries.length)
    return (
      <p className="muted">
        No changes to review yet. Choose Edit changes to add the requested
        details.
      </p>
    );
  return (
    <div className="comparison" role="table" aria-label="Policy changes">
      <div className="comparison-head" role="row">
        <span role="columnheader">Detail</span>
        <span role="columnheader">{applied ? "Previous" : "Current"}</span>
        <span role="columnheader">{applied ? "Updated" : "Proposed"}</span>
      </div>
      {entries.map(([key, value]) => (
        <div className="comparison-row" role="row" key={key}>
          <strong role="cell">{fields[key as keyof typeof fields]}</strong>
          <span
            role="cell"
            className="before-value"
            data-label={applied ? "Previous" : "Current"}
          >
            {proposal.before[key] || "Not available"}
          </span>
          <span
            role="cell"
            className="after-value"
            data-label={applied ? "Updated" : "Proposed"}
          >
            <ArrowRight size={14} />
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}
function ReviewSummary({
  record,
  proposal,
  edit,
  disabled,
}: {
  record: Case;
  proposal: Proposal;
  edit?: () => void;
  disabled: boolean;
}) {
  return (
    <>
      <div
        className={`validation-summary ${proposal.findings.length ? "has-findings" : ""}`}
      >
        {proposal.findings.length ? (
          <Clock3 size={19} />
        ) : (
          <ShieldCheck size={19} />
        )}
        <div>
          <strong>
            {proposal.findings.length
              ? `${proposal.findings.length} detail${proposal.findings.length === 1 ? " needs" : "s need"} your attention`
              : "Required checks passed"}
          </strong>
          <p>
            {proposal.findings.length
              ? "Add or correct the information below to continue."
              : "No issues found in the required checks."}
          </p>
        </div>
      </div>
      {proposal.findings.length > 0 && (
        <ul className="findings">
          {proposal.findings.map((finding, i) => (
            <li key={i}>
              <strong>{finding.code.replaceAll("_", " ")}</strong>
              <p>{finding.message}</p>
            </li>
          ))}
        </ul>
      )}
      <section className="section-block">
        <div className="section-heading">
          <div>
            <h3>
              {record.status === "completed"
                ? "Applied changes"
                : "Proposed changes"}
              <span className="version-tag">v{proposal.version}</span>
            </h3>
            <p>
              {record.status === "completed"
                ? "These changes are now saved on the policy."
                : "Check the details below before approving."}
            </p>
          </div>
          {edit && (
            <button
              className="text-button"
              disabled={disabled}
              onClick={(event) => {
                event.currentTarget.focus();
                edit?.();
              }}
            >
              Edit changes
            </button>
          )}
        </div>
        <Comparison
          proposal={proposal}
          applied={record.status === "completed"}
        />
      </section>
      <EvidencePanel record={record} proposal={proposal} compact />
    </>
  );
}
function EvidencePanel({
  record,
  proposal,
  compact = false,
}: {
  record: Case;
  proposal?: Proposal;
  compact?: boolean;
}) {
  const evidence = proposal?.evidence;
  const source = evidence?.source;
  return (
    <section className="evidence-card">
      <div className="section-label">
        <FileCheck2 size={16} />
        Proof of address
        {source && (
          <span className="pill">
            {source.kind === "synthetic_fixture"
              ? "Sample document"
              : "Uploaded document"}
          </span>
        )}
      </div>
      {!evidence ? (
        <p className="muted">
          {proposal?.changes.mailing_address
            ? "Proof of address is required for this change."
            : "No document needed for email or phone changes."}
        </p>
      ) : (
        <>
          <strong>
            {source?.filename ||
              source?.id?.replaceAll("-", " ") ||
              "Selected evidence"}
          </strong>
          <p>
            {evidence.name || "Name could not be read"}
            <br />
            {evidence.address || "Address could not be read"}
          </p>
          <div className="evidence-footer">
            <span>
              {evidence.certain && evidence.readable
                ? "Document text checked"
                : "Needs verification"}
              {source?.kind !== "synthetic_fixture" && source?.page
                ? ` · Page ${source.page}`
                : ""}
            </span>
            {source?.kind === "attachment" && (
              <a
                href={`/api/backend/cases/${record.id}/attachments/${source.id}/content`}
                download
              >
                Download document <ArrowDownToLine size={13} />
              </a>
            )}
          </div>
          {!compact && evidence.reason && <p>{evidence.reason}</p>}
        </>
      )}
    </section>
  );
}
