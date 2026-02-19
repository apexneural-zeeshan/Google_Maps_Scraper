"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getBatch, deleteBatch, BatchDetailResponse, JobResponse } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-yellow-100 text-yellow-700",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? "bg-gray-100 text-gray-700"}`}
    >
      {status}
    </span>
  );
}

function LayerDots({ job }: { job: JobResponse }) {
  const dot = (status: string) => {
    const colors: Record<string, string> = {
      idle: "bg-gray-300",
      running: "bg-blue-400 animate-pulse",
      completed: "bg-green-500",
      failed: "bg-red-500",
    };
    return colors[status] ?? "bg-gray-300";
  };
  return (
    <div className="flex items-center gap-1" title="L1 / L2 / L3">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot(job.layer1_status)}`} />
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot(job.layer2_status)}`} />
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot(job.layer3_status)}`} />
    </div>
  );
}

export default function BatchDetailPage() {
  const params = useParams();
  const router = useRouter();
  const batchId = params.id as string;

  const [data, setData] = useState<BatchDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchBatch = useCallback(async () => {
    try {
      const result = await getBatch(batchId);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load batch");
    } finally {
      setLoading(false);
    }
  }, [batchId]);

  useEffect(() => {
    fetchBatch();
    const interval = setInterval(fetchBatch, 5000);
    return () => clearInterval(interval);
  }, [fetchBatch]);

  // Stop polling once batch is terminal
  const isTerminal =
    data?.batch.status === "completed" ||
    data?.batch.status === "failed" ||
    data?.batch.status === "cancelled";

  useEffect(() => {
    if (isTerminal) return;
    const interval = setInterval(fetchBatch, 5000);
    return () => clearInterval(interval);
  }, [isTerminal, fetchBatch]);

  const handleDelete = async () => {
    if (!confirm("Delete this batch and all its jobs? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await deleteBatch(batchId);
      router.push("/jobs");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete batch");
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-red-700">
        {error}
      </div>
    );
  }

  if (!data) return null;

  const { batch, jobs } = data;
  const completedCount = batch.completed_jobs;
  const failedCount = batch.failed_jobs;
  const totalCount = batch.total_jobs;
  const progressPct = totalCount > 0 ? Math.round(((completedCount + failedCount) / totalCount) * 100) : 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link
            href="/jobs"
            className="mb-2 inline-block text-sm text-[var(--text-secondary)] hover:text-[var(--text)]"
          >
            &larr; Back to Jobs
          </Link>
          <h1 className="text-2xl font-bold text-[var(--text)]">
            {batch.name || "Unnamed Batch"}
          </h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Created {new Date(batch.created_at).toLocaleString()}
            {batch.user_email && <> &middot; {batch.user_email}</>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={batch.status} />
          <button
            type="button"
            className="rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? "Deleting..." : "Delete Batch"}
          </button>
        </div>
      </div>

      {/* Progress Card */}
      <div className="card">
        <div className="mb-3 flex items-center justify-between text-sm">
          <span className="text-[var(--text-secondary)]">
            Progress: {completedCount} completed, {failedCount} failed of {totalCount} jobs
          </span>
          <span className="font-medium text-[var(--text)]">{progressPct}%</span>
        </div>
        <div className="h-3 w-full overflow-hidden rounded-full bg-[var(--bg-secondary)]">
          <div className="flex h-full">
            {completedCount > 0 && (
              <div
                className="bg-green-500 transition-all duration-500"
                style={{ width: `${(completedCount / totalCount) * 100}%` }}
              />
            )}
            {failedCount > 0 && (
              <div
                className="bg-red-500 transition-all duration-500"
                style={{ width: `${(failedCount / totalCount) * 100}%` }}
              />
            )}
          </div>
        </div>
        <div className="mt-2 flex items-center gap-4 text-xs text-[var(--text-secondary)]">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-green-500" /> Completed ({completedCount})
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-red-500" /> Failed ({failedCount})
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-gray-300" /> Remaining ({totalCount - completedCount - failedCount})
          </span>
        </div>
      </div>

      {/* Jobs Table */}
      <div className="card overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--bg-secondary)]">
                <th className="px-4 py-3 text-xs font-medium text-[var(--text-secondary)]">#</th>
                <th className="px-4 py-3 text-xs font-medium text-[var(--text-secondary)]">Keyword</th>
                <th className="px-4 py-3 text-xs font-medium text-[var(--text-secondary)]">Location</th>
                <th className="px-4 py-3 text-xs font-medium text-[var(--text-secondary)]">Status</th>
                <th className="px-4 py-3 text-xs font-medium text-[var(--text-secondary)]">Layers</th>
                <th className="px-4 py-3 text-xs font-medium text-[var(--text-secondary)]">Leads</th>
                <th className="px-4 py-3 text-xs font-medium text-[var(--text-secondary)]">Cost</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job, idx) => (
                <tr
                  key={job.id}
                  className="border-b border-[var(--border)] transition-colors hover:bg-[var(--bg-secondary)]"
                >
                  <td className="px-4 py-3 text-[var(--text-secondary)]">{idx + 1}</td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/jobs/${job.id}`}
                      className="font-medium text-primary-600 hover:underline"
                    >
                      {job.keyword}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-[var(--text-secondary)]">{job.location}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="px-4 py-3">
                    <LayerDots job={job} />
                  </td>
                  <td className="px-4 py-3">
                    {job.total_unique > 0 ? (
                      <span className="font-medium">{job.total_unique}</span>
                    ) : (
                      <span className="text-[var(--text-secondary)]">&mdash;</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[var(--text-secondary)]">
                    ${job.estimated_cost_usd.toFixed(3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
