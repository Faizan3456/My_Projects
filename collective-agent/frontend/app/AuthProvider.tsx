"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { setTokenProvider } from "@/lib/api";
import {
  authEnabled,
  currentAccount,
  getAccessToken,
  handleRedirect,
  signIn,
  signOut,
} from "@/lib/auth";

interface AuthState {
  /** Whether this deployment requires sign-in at all. */
  required: boolean;
  ready: boolean;
  signedIn: boolean;
  userName: string | null;
  error: string | null;
  signIn: () => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(!authEnabled);
  const [userName, setUserName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Every API call pulls its token from here, so a silent refresh happens on
  // whichever request needs it rather than on a timer.
  useEffect(() => {
    setTokenProvider(getAccessToken);
  }, []);

  useEffect(() => {
    if (!authEnabled) return;
    let cancelled = false;

    (async () => {
      try {
        await handleRedirect();
        const account = await currentAccount();
        if (cancelled) return;
        setUserName(account?.name ?? account?.username ?? null);
      } catch (cause) {
        if (cancelled) return;
        setError(
          cause instanceof Error ? cause.message : "Sign-in failed unexpectedly.",
        );
      } finally {
        if (!cancelled) setReady(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      required: authEnabled,
      ready,
      signedIn: !authEnabled || userName !== null,
      userName,
      error,
      signIn: () => {
        void signIn().catch((cause) =>
          setError(cause instanceof Error ? cause.message : "Sign-in failed."),
        );
      },
      signOut: () => {
        void signOut().catch((cause) =>
          setError(cause instanceof Error ? cause.message : "Sign-out failed."),
        );
      },
    }),
    [ready, userName, error],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Renders children only for a signed-in user; otherwise offers sign-in. */
export function SignInGate({ children }: { children: React.ReactNode }) {
  const { required, ready, signedIn, error, signIn: begin } = useAuth();
  const start = useCallback(() => begin(), [begin]);

  if (!required) return <>{children}</>;

  if (!ready) {
    return (
      <main className="shell">
        <section className="panel muted">
          <span className="spinner" /> Checking your sign-in…
        </section>
      </main>
    );
  }

  if (!signedIn) {
    return (
      <main className="shell">
        <section className="panel" style={{ maxWidth: 520 }}>
          <h2>Sign in required</h2>
          <p className="small">
            This service runs agents against real provider API keys, so it is
            restricted to accounts in the OpenEdge Technologies directory.
          </p>
          {error && (
            <p className="small" style={{ color: "var(--danger)" }}>
              {error}
            </p>
          )}
          <button onClick={start}>Sign in with Microsoft</button>
        </section>
      </main>
    );
  }

  return <>{children}</>;
}
