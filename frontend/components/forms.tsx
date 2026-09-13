"use client";

import { useState, type FormEvent } from "react";
import { FileUp, Sparkles } from "lucide-react";
import {
  api,
  fields,
  type Attachment,
  type Case,
  type Changes,
  type Fixtures,
  type Health,
  type Intake,
} from "@/lib/types";
import { Dialog, Notice } from "./primitives";

export function ChangeFields({
  values,
  setValues,
}: {
  values: Changes;
  setValues: (value: Changes) => void;
}) {
  return (
    <div className="field-grid">
      {Object.entries(fields).map(([key, label]) => (
        <label
          key={key}
          className={key === "mailing_address" ? "span-two" : ""}
        >
          {label}
          <input
            name={key}
            type={key === "email" ? "email" : "text"}
            maxLength={
              key === "mailing_address" ? 500 : key === "email" ? 254 : 50
            }
            value={values[key as keyof Changes] || ""}
            onChange={(e) => setValues({ ...values, [key]: e.target.value })}
            placeholder="Leave blank to keep unchanged"
          />
        </label>
      ))}
    </div>
  );
}
const clean = (values: Changes) =>
  Object.fromEntries(
    Object.entries(values)
      .filter(([, value]) => value?.trim())
      .map(([key, value]) => [key, value!.trim()]),
  );

export function IntakeDialog({
  fixtures,
  health,
  close,
  saved,
}: {
  fixtures: Fixtures;
  health: Health | null;
  close: () => void;
  saved: (id: string) => void;
}) {
  const [input, setInput] = useState<Intake>({
    broker_id: fixtures.brokers[0].id,
    original_request: "",
  });
  const [changes, setChanges] = useState<Changes>({});
  const [manual, setManual] = useState(health?.extraction === "unconfigured");
  const [file, setFile] = useState<File | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function sample(index: string) {
    if (index === "") return;
    const value = fixtures.samples[Number(index)].intake;
    setInput(value);
    setChanges(value.changes || {});
    setManual(Boolean(value.changes));
    setFile(null);
    setError("");
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    let id = createdId;
    try {
      if (file && (file.size > 5 * 1024 * 1024 || file.size === 0))
        throw new Error("Choose a nonempty PDF up to 5 MB.");
      if (!id) {
        const payload: Intake = {
          broker_id: input.broker_id,
          original_request: input.original_request,
        };
        if (input.policy_number?.trim())
          payload.policy_number = input.policy_number.trim();
        if (input.evidence_id) payload.evidence_id = input.evidence_id;
        if (manual) {
          payload.changes = clean(changes);
          if (!Object.keys(payload.changes).length)
            throw new Error("Enter at least one requested change.");
        }
        const result = await api<Case>("backend/cases", "POST", payload);
        id = result.id;
        setCreatedId(id);
      }
      if (file && !uploaded) {
        const form = new FormData();
        form.append("file", file);
        await api(`backend/cases/${id}/attachments`, "POST", form);
        setUploaded(true);
      }
      await api(`backend/cases/${id}/process`, "POST");
      saved(id);
      close();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="New policy request" close={close} busy={busy}>
      <form onSubmit={submit} className="dialog-body">
        <p className="muted">
          Paste a broker request or start with a fictional example. You’ll
          review every change before it is applied.
        </p>
        {error && (
          <Notice>
            {error}
            {createdId && (
              <p>
                The request is saved. Retry below, or close this window and open
                it in the queue.
              </p>
            )}
          </Notice>
        )}
        <fieldset disabled={busy || Boolean(createdId)}>
          <label className="sample-select">
            <Sparkles size={16} /> Try a sample
            <select defaultValue="" onChange={(e) => sample(e.target.value)}>
              <option value="">Choose a scenario…</option>
              {fixtures.samples.map((item, i) => (
                <option key={item.title} value={i}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          <div className="field-grid">
            <label>
              Simulated broker
              <select
                value={input.broker_id}
                onChange={(e) =>
                  setInput({ ...input, broker_id: e.target.value })
                }
              >
                {fixtures.brokers.map((broker) => (
                  <option key={broker.id} value={broker.id}>
                    {broker.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Policy number <span className="optional">if known</span>
              <input
                value={input.policy_number || ""}
                maxLength={80}
                placeholder="e.g. DEMO-1001"
                onChange={(e) =>
                  setInput({ ...input, policy_number: e.target.value })
                }
              />
            </label>
          </div>
          <label>
            Original request
            <textarea
              required
              rows={5}
              maxLength={20000}
              placeholder="Hi, please update the email for policy DEMO-1001 to…"
              value={input.original_request}
              onChange={(e) =>
                setInput({ ...input, original_request: e.target.value })
              }
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={manual}
              onChange={(e) => setManual(e.target.checked)}
            />
            Enter the requested changes myself
          </label>
          {manual ? (
            <ChangeFields values={changes} setValues={setChanges} />
          ) : (
            <p className="field-help">
              The configured text model will extract the requested contact
              changes.
              {health?.extraction === "unconfigured" &&
                " No model is currently connected; enter changes yourself to run this demo."}
            </p>
          )}
          <label>
            Sample evidence
            <select
              value={input.evidence_id || ""}
              onChange={(e) =>
                setInput({ ...input, evidence_id: e.target.value || undefined })
              }
            >
              <option value="">No sample evidence</option>
              {Object.keys(fixtures.evidence).map((id) => (
                <option key={id} value={id}>
                  {id.replaceAll("-", " ")} (synthetic fixture)
                </option>
              ))}
            </select>
          </label>
        </fieldset>
        <label className="upload">
          <FileUp size={20} />
          <span>
            Attach a text PDF{" "}
            <span className="optional">optional · up to 5 MB</span>
          </span>
          <input
            aria-label="Attach a text PDF"
            type="file"
            accept="application/pdf,.pdf"
            disabled={busy || uploaded}
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <small>
            A PDF replaces sample evidence. Scans and image inspection are not
            supported yet.
          </small>
        </label>
        <div className="dialog-actions">
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => {
              if (createdId) saved(createdId);
              close();
            }}
          >
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy
              ? "Saving request…"
              : createdId
                ? "Retry remaining steps"
                : "Create & process request"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export function ReviewDialog({
  kind,
  record,
  fixtures,
  close,
  changed,
  failed,
}: {
  kind: "edit" | "reject" | "reply";
  record: Case;
  fixtures: Fixtures;
  close: () => void;
  changed: (record: Case, message: string) => void;
  failed: (error: unknown) => void;
}) {
  // Snapshot at opening: polling must never silently update the version being submitted.
  const [snapshot] = useState(record);
  const [changes, setChanges] = useState<Changes>(
    snapshot.proposals.at(-1)?.changes || {},
  );
  const [text, setText] = useState("");
  const [policy, setPolicy] = useState(snapshot.policy_number || "");
  const [evidence, setEvidence] = useState("keep");
  const [file, setFile] = useState<File | null>(null);
  const [uploadedId, setUploadedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      let path: string;
      let payload: object;
      if (kind === "edit") {
        const values = clean(changes);
        if (!Object.keys(values).length)
          throw new Error("Keep at least one requested change.");
        path = "proposal";
        payload = {
          expected_version: snapshot.current_version,
          changes: values,
        };
      } else if (kind === "reject") {
        path = "reject";
        payload = { version: snapshot.current_version, reason: text };
      } else {
        let bound = uploadedId;
        if (file && !bound) {
          const form = new FormData();
          form.append("file", file);
          bound = (
            await api<Attachment>(
              `backend/cases/${snapshot.id}/attachments`,
              "POST",
              form,
            )
          ).id;
          setUploadedId(bound);
        }
        path = "replies";
        payload = {
          expected_version: snapshot.current_version,
          text,
          ...(policy.trim() ? { policy_number: policy.trim() } : {}),
          ...(bound
            ? { evidence_id: bound }
            : evidence !== "keep"
              ? { evidence_id: evidence === "none" ? null : evidence }
              : {}),
        };
      }
      const result = await api<Case>(
        `backend/cases/${snapshot.id}/${path}`,
        kind === "edit" ? "PUT" : "POST",
        payload,
      );
      changed(
        result,
        kind === "reject"
          ? "Request rejected. No policy update was applied."
          : `Version ${result.current_version} created. Any previous approval has been invalidated.`,
      );
      close();
    } catch (e) {
      setError((e as Error).message);
      if (typeof e === "object" && e && "status" in e && e.status === 409)
        setStale(true);
      failed(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      title={
        kind === "edit"
          ? "Edit proposed changes"
          : kind === "reject"
            ? "Reject request"
            : "Add information"
      }
      close={close}
      busy={busy}
    >
      <form className="dialog-body" onSubmit={submit}>
        <p className="muted">
          {kind === "reject"
            ? "Record why this request should not proceed. Rejection closes the case."
            : "This creates a new version and requires fresh review."}{" "}
          Reviewing version {snapshot.current_version}.
        </p>
        {error && (
          <Notice>
            {error}
            {stale && (
              <p>
                Close this dialog, refresh the case, and review the latest
                version before trying again.
              </p>
            )}
          </Notice>
        )}
        <fieldset disabled={busy || stale}>
          {kind === "edit" ? (
            <ChangeFields values={changes} setValues={setChanges} />
          ) : (
            <label>
              {kind === "reject"
                ? "Reason for rejection"
                : "Reply or clarification"}
              <textarea
                required
                rows={4}
                maxLength={kind === "reject" ? 1000 : 20000}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
          )}
          {kind === "reply" && (
            <>
              <label>
                Explicit policy number
                <input
                  value={policy}
                  maxLength={80}
                  onChange={(e) => setPolicy(e.target.value)}
                />
              </label>
              <label>
                Supporting evidence
                <select
                  value={evidence}
                  disabled={Boolean(uploadedId)}
                  onChange={(e) => setEvidence(e.target.value)}
                >
                  <option value="keep">Keep current evidence</option>
                  <option value="none">Remove evidence</option>
                  {snapshot.attachments.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.filename}
                    </option>
                  ))}
                  {Object.keys(fixtures.evidence).map((id) => (
                    <option key={id} value={id}>
                      {id.replaceAll("-", " ")} (synthetic fixture)
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Upload corrected PDF
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  disabled={Boolean(uploadedId)}
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </label>
              <p className="field-help">
                An uploaded PDF replaces the selected evidence when this reply
                is saved.
              </p>
            </>
          )}
        </fieldset>
        <div className="dialog-actions">
          <button
            type="button"
            className="button secondary"
            onClick={close}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            className={`button ${kind === "reject" ? "destructive" : "primary"}`}
            disabled={busy || stale}
          >
            {busy
              ? "Saving…"
              : kind === "edit"
                ? "Save new version"
                : kind === "reject"
                  ? "Reject request"
                  : "Save reply & revalidate"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
