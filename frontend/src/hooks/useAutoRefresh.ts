import { useEffect, useRef, useCallback } from 'react';

/**
 * Custom event dispatched when the browser tab becomes visible again.
 * Widgets listen for this to trigger an immediate data refresh.
 */
const VISIBILITY_REFRESH_EVENT = 'jarvis-visibility-refresh';

/**
 * Installs a global visibility-change listener that fires a custom event
 * when the user returns to the tab.  Call once at the app/panel level.
 */
export function useVisibilityRefreshEmitter() {
  useEffect(() => {
    const handler = () => {
      if (document.visibilityState === 'visible') {
        window.dispatchEvent(new CustomEvent(VISIBILITY_REFRESH_EVENT));
      }
    };
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);
}

/**
 * Sets up an interval that polls `fetchFn` every `intervalMs` milliseconds,
 * AND triggers an immediate refetch when the tab becomes visible.
 *
 * Pauses polling when the tab is hidden to save bandwidth.
 */
export function useAutoRefresh(fetchFn: () => void, intervalMs: number) {
  const intervalRef = useRef<ReturnType<typeof setInterval>>();
  const stableFetch = useCallback(fetchFn, [fetchFn]);

  useEffect(() => {
    // Start polling
    intervalRef.current = setInterval(stableFetch, intervalMs);

    // Pause when hidden, resume when visible
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        stableFetch();
        // Restart interval so next tick is a full interval away
        clearInterval(intervalRef.current);
        intervalRef.current = setInterval(stableFetch, intervalMs);
      } else {
        clearInterval(intervalRef.current);
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      clearInterval(intervalRef.current);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [stableFetch, intervalMs]);
}
