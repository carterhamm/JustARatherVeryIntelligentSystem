/**
 * WebAuthn / Passkey utilities for browser-side credential operations.
 * Uses @simplewebauthn/browser under the hood.
 */
import {
  startRegistration,
  startAuthentication,
} from '@simplewebauthn/browser';

/**
 * Trigger the browser's passkey registration ceremony.
 * Returns the credential JSON to send to the server.
 */
export async function createPasskey(
  options: any,
): Promise<any> {
  return startRegistration(options);
}

/**
 * Trigger the browser's passkey authentication ceremony.
 * Returns the assertion JSON to send to the server.
 */
export async function authenticatePasskey(
  options: any,
): Promise<any> {
  return startAuthentication(options);
}

/**
 * Check if WebAuthn is available in the current browser.
 */
export function isWebAuthnAvailable(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.PublicKeyCredential !== 'undefined'
  );
}
