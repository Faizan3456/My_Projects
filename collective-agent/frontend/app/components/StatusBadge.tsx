import type { ContextStatus } from "@/lib/types";

const LABELS: Record<ContextStatus, string> = {
  active: "Active",
  blocked: "Blocked",
  handover_required: "Handover required",
  done: "Done",
};

export function StatusBadge({ status }: { status: ContextStatus }) {
  return <span className={`badge ${status}`}>{LABELS[status]}</span>;
}
