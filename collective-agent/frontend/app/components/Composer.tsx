"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  canSend: boolean;
  busy: boolean;
  manual: boolean;
  onToggleManual: (manual: boolean) => void;
  onRun: (message: string) => Promise<void>;
}

/** A text box, plus how the message gets to the model. */
export function Composer({
  canSend,
  busy,
  manual,
  onToggleManual,
  onRun,
}: Props) {
  const [message, setMessage] = useState("");
  const boxRef = useRef<HTMLTextAreaElement>(null);

  // Grow with the text, up to a point, the way a chat input should.
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 220)}px`;
  }, [message]);

  async function run() {
    if (!canSend || busy) return;
    const text = message;
    setMessage("");
    try {
      await onRun(text);
    } catch {
      setMessage(text); // keep the typing if the turn failed
    } finally {
      boxRef.current?.focus();
    }
  }

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          ref={boxRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={1}
          placeholder={manual ? "Message… (you'll paste this in)" : "Message…"}
          disabled={busy}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void run();
            }
          }}
        />
        <button
          className="send"
          onClick={run}
          disabled={busy || !canSend}
          aria-label={manual ? "Build briefing" : "Send"}
          title={manual ? "Build the briefing to paste" : "Send (Enter)"}
        >
          {busy ? <span className="spinner" /> : <ArrowUp />}
        </button>
      </div>

      {/* How the message reaches the model: its API key, or your own login. */}
      <div className="mode-switch" role="group" aria-label="How to send">
        <button
          className={manual ? "mode" : "mode on"}
          onClick={() => onToggleManual(false)}
          disabled={busy}
        >
          API key
        </button>
        <button
          className={manual ? "mode on" : "mode"}
          onClick={() => onToggleManual(true)}
          disabled={busy}
          title="Copy the briefing into a chat window you're signed in to"
        >
          My login
        </button>
      </div>
    </div>
  );
}

function ArrowUp() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M8 13V3M8 3L3.5 7.5M8 3l4.5 4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
