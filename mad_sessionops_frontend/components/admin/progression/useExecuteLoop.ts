"use client";

import { useCallback, useRef, useState } from "react";
import {
  executeSchool,
  type SchoolResult,
  type SchoolRunStatus,
} from "@/lib/api/services/progression.service";

export type LoopState = "idle" | "running" | "stopped" | "done";

/**
 * Executes a run's schools ONE AT A TIME (one backend transaction per request, so
 * no request is long-running — F-M10-9). A school's own failure is recorded and
 * the loop continues; a network/request error stops the loop and leaves the
 * remaining schools queued for Resume from the Runs tab.
 */
export function useExecuteLoop(onSchoolDone?: (result: SchoolResult) => void) {
  const [statuses, setStatuses] = useState<Record<number, SchoolRunStatus>>({});
  const [errors, setErrors] = useState<Record<number, string | null>>({});
  const [state, setState] = useState<LoopState>("idle");
  const [stopMessage, setStopMessage] = useState<string | null>(null);
  const cancelled = useRef(false);

  const seed = useCallback((initial: Record<number, SchoolRunStatus>) => {
    setStatuses(initial);
    setErrors({});
  }, []);

  const setOne = useCallback((result: SchoolResult) => {
    setStatuses((prev) => ({ ...prev, [result.schoolId]: result.status }));
    setErrors((prev) => ({ ...prev, [result.schoolId]: result.error }));
  }, []);

  const run = useCallback(
    async (runId: number, schoolIds: number[]) => {
      cancelled.current = false;
      setState("running");
      setStopMessage(null);
      for (const schoolId of schoolIds) {
        if (cancelled.current) break;
        setStatuses((prev) => ({ ...prev, [schoolId]: "running" }));
        try {
          const result = await executeSchool(runId, schoolId);
          setOne(result);
          onSchoolDone?.(result);
        } catch (caught) {
          setStatuses((prev) => ({ ...prev, [schoolId]: "queued" }));
          const message = (caught as { message?: string })?.message ?? "Request failed.";
          setStopMessage(
            `${message} Progress stopped; the remaining schools are still queued. ` +
              "Resume from the Runs tab."
          );
          setState("stopped");
          return;
        }
      }
      setState("done");
    },
    [onSchoolDone, setOne]
  );

  const cancel = useCallback(() => {
    cancelled.current = true;
  }, []);

  return { statuses, errors, state, stopMessage, seed, setOne, run, cancel };
}
