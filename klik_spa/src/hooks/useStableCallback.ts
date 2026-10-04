import { useCallback, useLayoutEffect, useRef } from "react";

/**
 * A callback whose identity never changes but which always runs the latest closure, so a
 * memoized child is not redrawn each time its parent rebuilds the handler.
 */
export function useStableCallback<A extends unknown[], R>(fn: (...args: A) => R): (...args: A) => R {
  const latest = useRef(fn);
  useLayoutEffect(() => {
    latest.current = fn;
  });
  return useCallback((...args: A) => latest.current(...args), []);
}
