"use client";

import { JobResponse, cancelJob } from "@/lib/api";
import { useState } from "react";

interface JobStatusProps {
  job: JobResponse;
}

const STEP_LABELS: Record<string, string> = {
  pending: "Queued",
  geocoding: "Geocoding",
  grid_search: "Grid",
  playwright: "Scraping",
  serp_api: "SerpAPI",
  dedup: "Dedup",
  enriching: "Enriching",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

const STEPS = [
  "pending",
  "geocoding",
  "grid_search",
  "playwright",
  "serp_api",
  "dedup",
  "enriching",
  "completed",
];

function getStepIndex(status: string): number {
  const idx = STEPS.indexOf(status);
  return idx >= 0 ? idx : 0;
}

export default function JobStatusComponent({ job }: JobStatusProps) {
  const [cancelling, setCancelling] = useState(false);

  const isTerminal = ["completed", "failed", "cancelled"].includes(job.status);
  const isFailed = job.status === "failed";
  const currentStepIndex = getStepIndex(job.status);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await cancelJob(job.id);
    } catch {
      // Job may already be done
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="card flex flex-col gap-5">
      {/* Progress Bar */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-[var(--text)]">
            {job.current_step || STEP_LABELS[job.status] || job.status}
          </span>
          <span className="text-sm font-semibold text-primary-600">
            {job.progress}%
          </span>
        </div>
        <div className="h-3 overflow-hidden rounded-full bg-[var(--bg-secondary)]">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              isFailed
                ? "bg-red-500"
                : isTerminal
                  ? "bg-green-500"
                  : "bg-primary-500"
            }`}
            style={{ width: `${job.progress}%` }}
          />
        </div>
      </div>

      {/* Step Indicators */}
      <div className="flex items-center justify-between overflow-x-auto">
        {STEPS.map((step, i) => {
          const isActive = i === currentStepIndex;
          const isDone = i < currentStepIndex || job.status === "completed";

          return (
            <div key={step} className="flex flex-col items-center gap-1">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium transition-colors ${
                  isDone
                    ? "bg-green-100 text-green-700"
                    : isActive
                      ? "bg-primary-100 text-primary-700"
                      : "bg-[var(--bg-secondary)] text-[var(--text-secondary)]"
                }`}
              >
                {isDone ? "\u2713" : i + 1}
              </div>
              <span
                className={`whitespace-nowrap text-[10px] ${
                  isActive
                    ? "font-semibold text-primary-600"
                    : "text-[var(--text-secondary)]"
                }`}
              >
                {STEP_LABELS[step]}
              </span>
            </div>
          );
        })}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg bg-[var(--bg-secondary)] p-3">
          <div className="text-xs text-[var(--text-secondary)]">Found</div>
          <div className="text-lg font-semibold text-[var(--text)]">
            {job.total_found}
          </div>
        </div>
        <div className="rounded-lg bg-[var(--bg-secondary)] p-3">
          <div className="text-xs text-[var(--text-secondary)]">Unique</div>
          <div className="text-lg font-semibold text-[var(--text)]">
            {job.total_unique}
          </div>
        </div>
        <div className="rounded-lg bg-[var(--bg-secondary)] p-3">
          <div className="text-xs text-[var(--text-secondary)]">API Calls</div>
          <div className="text-lg font-semibold text-[var(--text)]">
            {job.places_api_calls + job.serp_api_calls}
          </div>
        </div>
        <div className="rounded-lg bg-[var(--bg-secondary)] p-3">
          <div className="text-xs text-[var(--text-secondary)]">Est. Cost</div>
          <div className="text-lg font-semibold text-[var(--text)]">
            ${job.estimated_cost_usd.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Error Message */}
      {isFailed && job.error_message && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {job.error_message}
        </div>
      )}

      {/* Cancel Button */}
      {!isTerminal && (
        <button
          className="btn-secondary self-end"
          onClick={handleCancel}
          disabled={cancelling}
        >
          {cancelling ? "Cancelling..." : "Cancel Job"}
        </button>
      )}
    </div>
  );
}
