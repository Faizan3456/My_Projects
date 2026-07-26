"use client";

import { useEffect, useRef } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Event } from "@/lib/types";

/**
 * The event log rendered as a conversation.
 *
 * Agent replies show the full text, not the stored summary — the summary exists
 * for the next agent's prompt, not for the person reading. Handovers and errors
 * appear inline as system notices so the moment one agent stopped and another
 * took over is visible in the flow.
 */

function fullReply(event: Event): string {
  const reply = event.payload?.reply;
  return typeof reply === "string" && reply.trim() ? reply : event.summary;
}

/** Strips the trailing memory-update block; it is plumbing, not an answer. */
function withoutMemoryBlock(text: string): string {
  return text
    .replace(/```json\s*\{[\s\S]*?"(summary|next_step)"[\s\S]*?\}\s*```\s*$/i, "")
    .trimEnd();
}

function Bubble({ event }: { event: Event }) {
  if (event.type === "user_message") {
    return (
      <div className="turn user">
        <div className="bubble">{event.summary}</div>
      </div>
    );
  }

  if (event.type === "agent_reply") {
    return (
      <div className="turn assistant">
        {/* Only the name — which AI answered is the point of this tool. The
            model id and timestamp were noise on top of the answer. */}
        <div className="who">
          <span className="agent-name">{event.agent_name}</span>
        </div>
        <div className="bubble md">
          <Markdown remarkPlugins={[remarkGfm]}>
            {withoutMemoryBlock(fullReply(event))}
          </Markdown>
        </div>
      </div>
    );
  }

  if (event.type === "handover") {
    const suggested = event.payload?.suggested_next_step;
    return (
      <div className="notice handover">
        <strong>{event.agent_name}</strong> stopped —{" "}
        {String(event.payload?.reason ?? event.summary)}
        {typeof suggested === "string" && suggested && (
          <div className="small muted">Resume at: {suggested}</div>
        )}
      </div>
    );
  }

  if (event.type === "error") {
    return (
      <div className="notice failure">
        <strong>{event.agent_name}</strong> failed — {event.summary}
      </div>
    );
  }

  if (event.type === "context_update" && event.agent_name) {
    return <div className="notice pickup">{event.summary}</div>;
  }

  return null;
}

interface Props {
  events: Event[];
  busy: boolean;
  pendingAgent: string | null;
}

export function Conversation({ events, busy, pendingAgent }: Props) {
  const scrollRef = useRef<HTMLElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // Events arrive newest-first from the API; a conversation reads oldest-first.
  const ordered = [...events].reverse().filter((e) => e.type !== "note");

  // Stay pinned to the newest message unless the reader has scrolled up.
  //
  // Scrolling once after render does not work: markdown tables and code blocks
  // change the content height after the effect runs, so any single scroll lands
  // near the top and the transcript looks stuck. Observing the content instead
  // means late layout, streamed replies and window resizes all keep the view at
  // the bottom.
  const pinned = useRef(true);

  useEffect(() => {
    const box = scrollRef.current;
    const content = contentRef.current;
    if (!box || !content) return;

    const stickToBottom = () => {
      if (pinned.current) box.scrollTop = box.scrollHeight;
    };

    // Only a deliberate gesture unpins. Listening to `scroll` instead would let
    // our own stickToBottom() calls unpin the view: they fire scroll events
    // while content is still growing, when the measured distance from the
    // bottom is briefly large.
    const onGesture = () => {
      const distanceFromBottom =
        box.scrollHeight - box.scrollTop - box.clientHeight;
      pinned.current = distanceFromBottom < 48;
    };

    const observer = new ResizeObserver(stickToBottom);
    // Both: the content grows as replies arrive, and the container changes size
    // when the window does. Watching only the content leaves the last message
    // clipped after a resize.
    observer.observe(content);
    observer.observe(box);
    for (const type of ["wheel", "touchmove", "keydown"] as const) {
      box.addEventListener(type, onGesture, { passive: true });
    }
    stickToBottom();

    return () => {
      observer.disconnect();
      for (const type of ["wheel", "touchmove", "keydown"] as const) {
        box.removeEventListener(type, onGesture);
      }
    };
  }, []);

  // A new message always returns the view to the bottom.
  useEffect(() => {
    pinned.current = true;
    const box = scrollRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [events.length, busy]);

  const empty = ordered.length === 0 && !busy;

  // One element, always mounted with its refs attached. Returning a different
  // element while the transcript is empty left the ResizeObserver with nothing
  // to observe on mount, so it never attached and resizes stopped re-pinning.
  return (
    <section
      className={empty ? "conversation empty" : "conversation"}
      ref={scrollRef}
    >
      <div className="stream" ref={contentRef}>
        {empty && <p className="greeting">What are we working on?</p>}
        {ordered.map((event) => (
          <Bubble key={event.id} event={event} />
        ))}
        {busy && (
          <div className="turn assistant">
            <div className="who">
              <span className="agent-name">{pendingAgent ?? "agent"}</span>
            </div>
            <div className="bubble thinking">
              <span className="spinner" /> working…
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
