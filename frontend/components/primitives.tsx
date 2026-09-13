"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { X, AlertCircle, CheckCircle2, Info } from "lucide-react";
import { type CaseStatus, statuses } from "@/lib/types";

export function Badge({ status }: { status: CaseStatus }) {
  const { label, tone } = statuses[status];
  return (
    <span className={`badge ${tone}`}>
      <span className="status-dot" />
      {label}
    </span>
  );
}
export function Notice({
  children,
  tone = "danger",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div
      className={`notice ${tone}`}
      role={tone === "danger" ? "alert" : "status"}
    >
      {tone === "success" ? (
        <CheckCircle2 size={18} />
      ) : (
        <AlertCircle size={18} />
      )}
      <div>{children}</div>
    </div>
  );
}
export function Dialog({
  title,
  children,
  close,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (trigger?.isConnected) trigger.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) close();
      }}
    >
      <div className="dialog-heading">
        <h2 id="dialog-title">{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={() => {
            if (!busy) close();
          }}
          aria-disabled={busy}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function date(value: string) {
  return new Date(
    value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`,
  ).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SupportNote({ id }: { id?: string }) {
  return (
    <p className="support-note" id={id}>
      <Info size={15} aria-hidden="true" />
      <span>
        Currently supports English text and PDFs with selectable text. Images
        and scanned documents aren’t supported yet.
      </span>
    </p>
  );
}
