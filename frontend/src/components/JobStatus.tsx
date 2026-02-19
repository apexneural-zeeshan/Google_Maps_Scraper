"use client";

import {
  JobResponse,
  cancelJob,
  enrichWithSerpapi,
  enrichWithOutscraper,
  deleteJob,
} from "@/lib/api";
import { useState } from "react";
import { useRouter } from "next/navigation";

interface JobStatusProps {
  job: JobResponse;
}

interface LayerCardProps {
  title: string;
  description: string;
  status: string;
  completedAt: string | null;
  onRun?: () => void;
  running: boolean;
  disabled: boolean;
  disabledReason?: string;
}

function LayerCard({
  title,
  description,
  status,
  completedAt,
  onRun,
  running,
  disabled,
  disabledReason,
}: LayerCardProps) {
  const statusColors: Record<string, string> = {
    idle: "bg-gray-100 text-gray-600",
    running: "bg-blue-100 text-blue-700",
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
  };

  const badgeStyle = statusColors[status] || statusColors.idle;

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--card-bg)] p-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-medium text-[var(--text)]">{title}</h3>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
            {description}
          </p>
        </div>
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${badgeStyle}`}
        >
          {status}
        </span>
      </div>

      {completedAt && (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">
          Completed {new Date(completedAt).toLocaleString()}
        </p>
      )}

      {onRun && (
        <button
          className="btn-secondary mt-3 w-full text-sm"
          onClick={onRun}
          disabled={disabled || running}
          title={disabledReason}
        >
          {running
            ? "Running..."
            : status === "completed"
              ? "Re-run"
              : status === "failed"
                ? "Retry"
                : "Run"}
        </button>
      )}
    </div>
  );
}

export default function JobStatusComponent({ job }: JobStatusProps) {
  const router = useRouter();
  const [cancelling, setCancelling] = useState(false);
  const [deletingJob, setDeletingJob] = useState(false);
  const [enrichingSerpapi, setEnrichingSerpapi] = useState(false);
  const [enrichingOutscraper, setEnrichingOutscraper] = useState(false);

  const isTerminal = ["completed", "failed", "cancelled"].includes(job.status);
  const isFailed = job.status === "failed";
  const layer1Done = job.layer1_status === "completed";

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

  const handleDelete = async () => {
    if (!confirm("Delete this job and all its leads?")) return;
    setDeletingJob(true);
    try {
      await deleteJob(job.id);
      router.push("/jobs");
    } catch {
      setDeletingJob(false);
    }
  };

  const handleEnrichSerpapi = async () => {
    setEnrichingSerpapi(true);
    try {
      await enrichWithSerpapi(job.id);
    } catch {
      // handle error
    } finally {
      setEnrichingSerpapi(false);
    }
  };

  const handleEnrichOutscraper = async () => {
    setEnrichingOutscraper(true);
    try {
      await enrichWithOutscraper(job.id);
    } catch {
      // handle error
    } finally {
      setEnrichingOutscraper(false);
    }
  };

  return (
    <div className="card flex flex-col gap-5">
      {/* Progress Bar */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-[var(--text)]">
            {job.current_step || (isTerminal ? job.status : "Processing...")}
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

      {/* Layer Cards */}
      <div className="grid gap-3 sm:grid-cols-3">
        <LayerCard
          title="Layer 1: Playwright"
          description="Free headless browser scraping"
          status={job.layer1_status}
          completedAt={job.layer1_completed_at}
          running={job.layer1_status === "running"}
          disabled={false}
        />
        <LayerCard
          title="Layer 2: SerpAPI"
          description="100 free searches/month"
          status={job.layer2_status}
          completedAt={job.layer2_completed_at}
          onRun={handleEnrichSerpapi}
          running={enrichingSerpapi || job.layer2_status === "running"}
          disabled={!layer1Done}
          disabledReason={!layer1Done ? "Layer 1 must complete first" : undefined}
        />
        <LayerCard
          title="Layer 3: Outscraper"
          description="Email & social enrichment"
          status={job.layer3_status}
          completedAt={job.layer3_completed_at}
          onRun={handleEnrichOutscraper}
          running={enrichingOutscraper || job.layer3_status === "running"}
          disabled={!layer1Done}
          disabledReason={!layer1Done ? "Layer 1 must complete first" : undefined}
        />
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

      {/* Action Buttons */}
      <div className="flex justify-end gap-2">
        {isTerminal && (
          <button
            type="button"
            className="rounded-lg border border-red-300 bg-red-50 px-4 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-100"
            onClick={handleDelete}
            disabled={deletingJob}
          >
            {deletingJob ? "Deleting..." : "Delete Job"}
          </button>
        )}
        {!isTerminal && (
          <button
            type="button"
            className="btn-secondary"
            onClick={handleCancel}
            disabled={cancelling}
          >
            {cancelling ? "Cancelling..." : "Cancel Job"}
          </button>
        )}
      </div>
    </div>
  );
}
