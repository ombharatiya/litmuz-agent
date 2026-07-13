// The Cognito email-OTP engine. All AWS SDK calls live here so the SDK is code-split behind a
// dynamic import (see lib/auth). Every operation is a public, unsigned Cognito call, so the
// client needs no AWS credentials. Email-OTP pattern: SignUp-first to unify new and returning
// users, USER_AUTH / EMAIL_OTP, id token stored client-side.

import {
  CognitoIdentityProviderClient,
  ConfirmSignUpCommand,
  InitiateAuthCommand,
  ResendConfirmationCodeCommand,
  RespondToAuthChallengeCommand,
  RevokeTokenCommand,
  SignUpCommand,
} from '@aws-sdk/client-cognito-identity-provider';

import { cognitoConfig, STORAGE_KEY } from './auth';

if (!cognitoConfig) {
  throw new Error('cognito engine loaded without configuration');
}
const config = cognitoConfig;
const client = new CognitoIdentityProviderClient({ region: config.region });

// Refresh the id token once it is within five minutes of expiry.
const FRESHNESS_WINDOW_MS = 5 * 60 * 1000;

export interface StoredTokens {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  expiresAt: number; // ms epoch, from the id token's exp claim
}

export interface Session {
  email: string;
  expiresAt: number;
}

export type BeginResult = { flow: 'signin' | 'signup'; session: string; email: string };

export class AuthError extends Error {
  constructor(
    message: string,
    public code: string,
  ) {
    super(message);
    this.name = 'AuthError';
  }
}

// --- storage ---

function readStore(): StoredTokens | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredTokens) : null;
  } catch {
    return null;
  }
}

function writeStore(tokens: StoredTokens): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
}

export function clearStore(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

// --- jwt (unverified, display only; the API Gateway authorizer verifies the signature) ---

function decodeJwt(token: string): Record<string, unknown> {
  const payload = token.split('.')[1];
  const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
  return JSON.parse(json) as Record<string, unknown>;
}

function storeAuthResult(result: {
  IdToken?: string;
  AccessToken?: string;
  RefreshToken?: string;
}): StoredTokens {
  if (!result.IdToken || !result.AccessToken) {
    throw new AuthError('Sign-in did not return tokens.', 'NoTokens');
  }
  const claims = decodeJwt(result.IdToken);
  const exp = typeof claims.exp === 'number' ? claims.exp : 0;
  const previous = readStore();
  const tokens: StoredTokens = {
    idToken: result.IdToken,
    accessToken: result.AccessToken,
    // Rotation is off on the pool, so a refresh response carries no new refresh token; keep the
    // one we have.
    refreshToken: result.RefreshToken ?? previous?.refreshToken,
    expiresAt: exp * 1000,
  };
  writeStore(tokens);
  return tokens;
}

export function currentSession(): Session | null {
  const tokens = readStore();
  if (!tokens) return null;
  try {
    const claims = decodeJwt(tokens.idToken);
    const email = typeof claims.email === 'string' ? claims.email : '';
    return { email, expiresAt: tokens.expiresAt };
  } catch {
    return null;
  }
}

// --- error mapping ---

function nameOf(err: unknown): string {
  return err && typeof err === 'object' && 'name' in err ? String((err as { name: unknown }).name) : '';
}

const MESSAGES: Record<string, string> = {
  CodeMismatchException: 'That code is not right. Check the newest email.',
  ExpiredCodeException: 'That code has expired. Send a new one and try again.',
  NotAuthorizedException: 'Too many tries or an expired code. Wait a moment, then send a new one.',
  LimitExceededException: 'Too many attempts. Please wait a little while and try again.',
  TooManyRequestsException: 'Too many attempts. Please wait a little while and try again.',
  InvalidParameterException: 'Please enter a valid email address.',
};

function toAuthError(err: unknown): AuthError {
  const code = nameOf(err);
  return new AuthError(MESSAGES[code] ?? 'Something went wrong. Please try again.', code || 'Unknown');
}

// --- throwaway password (SignUp requires one; no user ever sees it) ---

function throwawayPassword(): string {
  const classes = [
    'ABCDEFGHJKLMNPQRSTUVWXYZ',
    'abcdefghijkmnpqrstuvwxyz',
    '23456789',
    '!@#$%^&*-_=+',
  ];
  const all = classes.join('');
  const bytes = new Uint32Array(32);
  crypto.getRandomValues(bytes);
  const chars = Array.from(bytes, (b, i) =>
    i < classes.length ? classes[i][b % classes[i].length] : all[b % all.length],
  );
  for (let i = chars.length - 1; i > 0; i--) {
    const j = crypto.getRandomValues(new Uint32Array(1))[0] % (i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join('');
}

// --- the flow ---

async function signUp(email: string): Promise<string | undefined> {
  const resp = await client.send(
    new SignUpCommand({
      ClientId: config.clientId,
      Username: email,
      Password: throwawayPassword(),
      UserAttributes: [{ Name: 'email', Value: email }],
    }),
  );
  return resp.Session;
}

async function initiateEmailOtp(email: string) {
  return client.send(
    new InitiateAuthCommand({
      AuthFlow: 'USER_AUTH',
      ClientId: config.clientId,
      AuthParameters: { USERNAME: email, PREFERRED_CHALLENGE: 'EMAIL_OTP' },
    }),
  );
}

// One email field for everyone: a new address signs up (Cognito emails a 6-digit confirmation
// code); a known address gets an 8-digit sign-in code.
export async function beginEmailAuth(rawEmail: string): Promise<BeginResult> {
  const email = rawEmail.trim().toLowerCase();
  try {
    const session = await signUp(email);
    return { flow: 'signup', session: session ?? '', email };
  } catch (err) {
    const code = nameOf(err);
    if (code !== 'UsernameExistsException') throw toAuthError(err);
  }

  try {
    const resp = await initiateEmailOtp(email);
    if (resp.ChallengeName === 'EMAIL_OTP' && resp.Session) {
      return { flow: 'signin', session: resp.Session, email };
    }
    throw new AuthError('Could not send a sign-in code.', 'OtpUnavailable');
  } catch (err) {
    // An unconfirmed prior sign-up: resend the confirmation code and finish as a sign-up.
    if (nameOf(err) === 'UserNotConfirmedException') {
      await client.send(
        new ResendConfirmationCodeCommand({ ClientId: config.clientId, Username: email }),
      );
      return { flow: 'signup', session: '', email };
    }
    if (err instanceof AuthError) throw err;
    throw toAuthError(err);
  }
}

// Returning user: exchange the 8-digit sign-in code for tokens. The session survives a wrong
// code, so retries reuse it.
export async function submitSignInOtp(
  email: string,
  code: string,
  session: string,
): Promise<Session> {
  try {
    const resp = await client.send(
      new RespondToAuthChallengeCommand({
        ClientId: config.clientId,
        ChallengeName: 'EMAIL_OTP',
        Session: session,
        ChallengeResponses: { USERNAME: email, EMAIL_OTP_CODE: code },
      }),
    );
    if (!resp.AuthenticationResult) throw new AuthError('Sign-in did not complete.', 'NoTokens');
    storeAuthResult(resp.AuthenticationResult);
    return currentSession()!;
  } catch (err) {
    if (err instanceof AuthError) throw err;
    throw toAuthError(err);
  }
}

// New user: confirm the 6-digit code, then silently trade the confirmation session for tokens
// (no second code). If that session is spent, fall back to a normal sign-in code.
export async function submitSignUpOtp(email: string, code: string): Promise<Session> {
  try {
    const confirm = await client.send(
      new ConfirmSignUpCommand({ ClientId: config.clientId, Username: email, ConfirmationCode: code }),
    );
    const session = confirm.Session;
    if (session) {
      const resp = await client.send(
        new InitiateAuthCommand({
          AuthFlow: 'USER_AUTH',
          ClientId: config.clientId,
          Session: session,
          AuthParameters: { USERNAME: email },
        }),
      );
      if (resp.AuthenticationResult) {
        storeAuthResult(resp.AuthenticationResult);
        return currentSession()!;
      }
    }
    // Session spent: request a fresh sign-in code and let the caller collect it.
    throw new AuthError('Please enter the sign-in code we just emailed.', 'AutoSignInFailed');
  } catch (err) {
    if (err instanceof AuthError) throw err;
    throw toAuthError(err);
  }
}

export async function resendCode(email: string, flow: 'signin' | 'signup'): Promise<string> {
  if (flow === 'signup') {
    await client.send(new ResendConfirmationCodeCommand({ ClientId: config.clientId, Username: email }));
    return '';
  }
  const resp = await initiateEmailOtp(email);
  return resp.Session ?? '';
}

// --- refresh + token access ---

async function refresh(tokens: StoredTokens): Promise<StoredTokens> {
  if (!tokens.refreshToken) throw new AuthError('Session expired.', 'NotAuthorizedException');
  const resp = await client.send(
    new InitiateAuthCommand({
      AuthFlow: 'REFRESH_TOKEN_AUTH',
      ClientId: config.clientId,
      AuthParameters: { REFRESH_TOKEN: tokens.refreshToken },
    }),
  );
  if (!resp.AuthenticationResult) throw new AuthError('Session expired.', 'NotAuthorizedException');
  return storeAuthResult(resp.AuthenticationResult);
}

async function freshTokens(): Promise<StoredTokens | null> {
  const tokens = readStore();
  if (!tokens) return null;
  if (Date.now() < tokens.expiresAt - FRESHNESS_WINDOW_MS) return tokens;
  try {
    return await refresh(tokens);
  } catch (err) {
    // Only a rejected refresh token ends the session; a transient network error keeps the
    // current tokens if they are still valid, and refresh is retried on the next call.
    if (nameOf(err) === 'NotAuthorizedException') {
      clearStore();
      return null;
    }
    return Date.now() < tokens.expiresAt ? tokens : null;
  }
}

export async function getIdToken(): Promise<string | null> {
  const tokens = await freshTokens();
  return tokens?.idToken ?? null;
}

export async function signOut(): Promise<void> {
  const tokens = readStore();
  if (tokens?.refreshToken) {
    client
      .send(new RevokeTokenCommand({ ClientId: config.clientId, Token: tokens.refreshToken }))
      .catch(() => {
        /* offline or already revoked; the local clear still stands */
      });
  }
  clearStore();
}
