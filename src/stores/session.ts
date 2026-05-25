import { writable } from 'svelte/store';
import { AuthManager, MANUAL_TOKEN_SNIPPET } from '../beatport/auth';
import { BeatportClient } from '../beatport/client';

export const auth = new AuthManager();
export const client = new BeatportClient(auth);
export const manualTokenSnippet = MANUAL_TOKEN_SNIPPET;

export const session = writable<{ connected: boolean }>({ connected: auth.isAuthenticated() });

function sync() {
  session.set({ connected: auth.isAuthenticated() });
}

export async function loginPopup(): Promise<void> {
  await auth.login();
  sync();
}

export function setManualToken(token: string): void {
  auth.setTokenManually(token.trim());
  sync();
}

export function logout(): void {
  auth.logout();
  sync();
}

// Called by UI error handlers when a BeatportAuthError surfaces mid-session.
export function refreshSession(): void {
  sync();
}
