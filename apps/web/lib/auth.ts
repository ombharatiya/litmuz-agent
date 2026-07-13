// Auth configuration and the outbound bearer header. The Cognito engine (lib/cognito) is
// loaded lazily so the AWS SDK stays out of the first-load bundle and is never fetched when
// auth is dark-shipped. When NEXT_PUBLIC_COGNITO_USER_POOL_ID / _CLIENT_ID are unset the app
// runs open and sends no token (the API keys to a default principal); the e2e suite runs in
// this mode. When set, a signed-in id token is attached to every request.

export interface CognitoConfig {
  userPoolId: string;
  clientId: string;
  // The AWS region is derived from the pool id ("ap-south-1_xxx" -> "ap-south-1"), so no
  // separate region value is needed.
  region: string;
}

function readConfig(): CognitoConfig | undefined {
  const userPoolId = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID?.trim();
  const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID?.trim();
  if (!userPoolId || !clientId) return undefined;
  return { userPoolId, clientId, region: userPoolId.split('_')[0] };
}

export const cognitoConfig = readConfig();
export const AUTH_ENABLED = cognitoConfig !== undefined;

export const STORAGE_KEY = cognitoConfig ? `litmuz.auth.${cognitoConfig.clientId}` : 'litmuz.auth';

// A cheap synchronous hint (no SDK) so anonymous visitors never load the auth engine.
export function hasStoredSession(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(STORAGE_KEY) !== null;
}

// The bearer header for outbound API calls. Resolves the freshest id token (refreshing if it
// is within the expiry window). Returns {} when auth is dark or no one is signed in.
export async function authHeaders(): Promise<Record<string, string>> {
  if (!AUTH_ENABLED || !hasStoredSession()) return {};
  const { getIdToken } = await import('./cognito');
  const token = await getIdToken();
  return token ? { authorization: `Bearer ${token}` } : {};
}
