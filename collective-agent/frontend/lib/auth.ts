/**
 * Microsoft Entra ID sign-in for the dashboard.
 *
 * The app registration is a SPA that calls its own API, so the token we send to
 * the backend is an access token for `api://<clientId>/access_as_user`, not an
 * id token. The backend verifies it against the tenant's signing keys.
 *
 * When no client id is configured the whole layer is inert, which matches the
 * backend's AUTH_MODE=disabled and keeps local development a one-command affair.
 */

import type {
  AccountInfo,
  AuthenticationResult,
  PublicClientApplication as PCA,
} from "@azure/msal-browser";

export const TENANT_ID = process.env.NEXT_PUBLIC_ENTRA_TENANT_ID ?? "";
export const CLIENT_ID = process.env.NEXT_PUBLIC_ENTRA_CLIENT_ID ?? "";

/** True when Entra sign-in is configured for this deployment. */
export const authEnabled = Boolean(TENANT_ID && CLIENT_ID);

export const API_SCOPE = `api://${CLIENT_ID}/access_as_user`;

let instance: PCA | null = null;
let initialising: Promise<PCA> | null = null;

/** Lazily create and initialise MSAL. Browser only — never on the server. */
export async function getMsal(): Promise<PCA> {
  if (instance) return instance;
  if (initialising) return initialising;

  initialising = (async () => {
    const { PublicClientApplication, LogLevel } = await import(
      "@azure/msal-browser"
    );
    const pca = new PublicClientApplication({
      auth: {
        clientId: CLIENT_ID,
        authority: `https://login.microsoftonline.com/${TENANT_ID}`,
        redirectUri: window.location.origin,
        navigateToLoginRequestUrl: true,
      },
      cache: {
        // sessionStorage keeps the token out of other tabs and clears on close.
        cacheLocation: "sessionStorage",
        storeAuthStateInCookie: false,
      },
      system: {
        loggerOptions: {
          logLevel: LogLevel.Error,
          loggerCallback: (_level, message, containsPii) => {
            if (!containsPii) console.error("[msal]", message);
          },
        },
      },
    });
    await pca.initialize();
    instance = pca;
    return pca;
  })();

  return initialising;
}

/** Completes a redirect sign-in, if we came back from one. */
export async function handleRedirect(): Promise<AuthenticationResult | null> {
  const pca = await getMsal();
  return pca.handleRedirectPromise();
}

export async function currentAccount(): Promise<AccountInfo | null> {
  const pca = await getMsal();
  return pca.getActiveAccount() ?? pca.getAllAccounts()[0] ?? null;
}

export async function signIn(): Promise<void> {
  const pca = await getMsal();
  await pca.loginRedirect({ scopes: [API_SCOPE] });
}

export async function signOut(): Promise<void> {
  const pca = await getMsal();
  const account = await currentAccount();
  await pca.logoutRedirect({
    account: account ?? undefined,
    postLogoutRedirectUri: window.location.origin,
  });
}

/**
 * An access token for the backend, refreshed silently when possible.
 * Falls back to an interactive redirect when the cache cannot satisfy it.
 */
export async function getAccessToken(): Promise<string | null> {
  if (!authEnabled) return null;
  const pca = await getMsal();
  const account = await currentAccount();
  if (!account) return null;

  try {
    const result = await pca.acquireTokenSilent({
      scopes: [API_SCOPE],
      account,
    });
    return result.accessToken;
  } catch (cause) {
    const { InteractionRequiredAuthError } = await import(
      "@azure/msal-browser"
    );
    if (cause instanceof InteractionRequiredAuthError) {
      await pca.acquireTokenRedirect({ scopes: [API_SCOPE], account });
      return null;
    }
    throw cause;
  }
}
