"use client";

import { useEffect, useRef, useState } from "react";
import type { AgentUsage } from "@/lib/types";

/**
 * The small usage readout in the header.
 *
 * It deliberately does not claim to show "credits remaining": Anthropic, OpenAI
 * and Google expose no balance endpoint to API keys. It shows what this system
 * has actually spent (recorded per turn) and the provider's own remaining
 * rate-limit allowance where one is published.
 */

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function Row({ usage }: { usage: AgentUsage }) {
  const { limits } = usage;
  const total = usage.input_tokens + usage.output_tokens;
  const remaining = limits.tokens_remaining;
  const ceiling = limits.tokens_limit;
  const pct =
    typeof remaining === "number" && typeof ceiling === "number" && ceiling > 0
      ? Math.max(0, Math.min(100, (remaining / ceiling) * 100))
      : null;

  return (
    <li className="usage-row">
      <div className="usage-head">
        <span className="usage-agent">{usage.agent}</span>
        {usage.is_active ? (
          <span className="badge active">ready</span>
        ) : (
          <span className="badge" title={usage.unavailable_reason ?? ""}>
            no key
          </span>
        )}
      </div>

      <div className="usage-detail small muted">
        {usage.turns > 0 ? (
          <>
            {usage.turns} turn{usage.turns === 1 ? "" : "s"} ·{" "}
            {compact(total)} tokens used
          </>
        ) : (
          <>not used yet</>
        )}
      </div>

      {pct !== null && (
        <>
          <div
            className="meter"
            role="meter"
            aria-valuenow={Math.round(pct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${usage.agent} tokens remaining`}
          >
            <span style={{ width: `${pct}%` }} />
          </div>
          <div className="usage-detail small muted">
            {compact(remaining as number)} of {compact(ceiling as number)}{" "}
            tokens left this window
          </div>
        </>
      )}

      {usage.stopped_reason && (
        <div className="usage-detail small warn-text">
          last stopped: {usage.stopped_reason}
        </div>
      )}
    </li>
  );
}

export function UsagePanel({ usage }: { usage: AgentUsage[] }) {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const ready = usage.filter((u) => u.is_active).length;
  const spent = usage.reduce(
    (sum, u) => sum + u.input_tokens + u.output_tokens,
    0,
  );

  return (
    <div className="usage" ref={boxRef}>
      <button
        className="usage-pill"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="dot" data-ok={ready > 0} />
        {ready}/{usage.length} ready
        {spent > 0 && <span className="muted"> · {compact(spent)} tokens</span>}
      </button>

      {open && (
        <div className="usage-pop" role="dialog" aria-label="Agent usage">
          <ul>
            {usage.map((u) => (
              <Row key={u.agent} usage={u} />
            ))}
          </ul>
          <p className="small muted usage-note">
            Providers do not publish a spendable credit balance to API keys.
            These are tokens spent here, plus each provider&apos;s own remaining
            rate-limit allowance where it reports one.
          </p>
        </div>
      )}
    </div>
  );
}
