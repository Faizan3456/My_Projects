"use client";

import { useState } from "react";
import type { ManualPrompt } from "@/lib/types";

/**
 * Use a chat window you are signed in to, without leaving the collective.
 *
 * Copy the briefing, paste it into ChatGPT or Claude, paste the answer back.
 * The answer is recorded as that agent's turn, so shared memory, handovers and
 * the transcript behave exactly as they do for an API agent — the only
 * difference is that you are the transport.
 */
interface Props {
  prompt: ManualPrompt;
  busy: boolean;
  onSubmit: (reply: string) => Promise<void>;
  onCancel: () => void;
}

export function ManualBridge({ prompt, busy, onSubmit, onCancel }: Props) {
  const [reply, setReply] = useState("");
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(prompt.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard permission can be refused; the textarea is selectable anyway.
      setCopied(false);
    }
  }

  return (
    <section className="bridge" aria-label="Manual bridge">
      <header className="bridge-head">
        <strong>
          Run this in <span className="agent-name">{prompt.agent_name}</span>
        </strong>
        <button className="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </header>

      <ol className="bridge-steps small">
        <li>
          <button onClick={copy}>{copied ? "Copied" : "Copy briefing"}</button>
          {prompt.chat_url && (
            <a
              className="ghost-link"
              href={prompt.chat_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open {prompt.agent_name} ↗
            </a>
          )}
        </li>
        <li>Paste it into the chat, then copy the answer.</li>
        <li>Paste the answer below and save it to memory.</li>
      </ol>

      <details className="bridge-preview">
        <summary className="small muted">Show the briefing</summary>
        <textarea readOnly value={prompt.text} rows={10} spellCheck={false} />
      </details>

      <textarea
        className="bridge-reply"
        value={reply}
        onChange={(e) => setReply(e.target.value)}
        rows={6}
        placeholder={`Paste ${prompt.agent_name}'s answer here…`}
        disabled={busy}
      />

      <div className="bridge-actions">
        <span className="small muted">
          Saved as a turn by {prompt.agent_name}, into the same shared memory.
        </span>
        <button
          onClick={() => void onSubmit(reply)}
          disabled={busy || !reply.trim()}
        >
          {busy ? <span className="spinner" /> : "Save answer"}
        </button>
      </div>
    </section>
  );
}
