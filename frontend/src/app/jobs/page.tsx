"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  listJobs,
  deleteJob,
  batchDeleteJobs,
  JobResponse,
} from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-600",
  pending: "bg-yellow-100 text-yellow-700",
};

function statusBadge(status: string) {
  const style = STATUS_STYLES[status] || "bg-blue-100 text-blue-700";
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${style}`}
    >
      {status}
    </span>
  );
}

function layerDot(layerStatus: string) {
  if (layerStatus === "completed") return "bg-green-500";
  if (layerStatus === "running") return "bg-blue-500 animate-pulse";
  if (layerStatus === "failed") return "bg-red-500";
  return "bg-gray-300";
}

export default function JobsListPage() {
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const pageSize = 20;

  const fetchJobs = useCallback(async () => {
    try {
      const data = await listJobs(page * pageSize, pageSize);
      setJobs(data.items);
      setTotal(data.total);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, [fetchJobs]);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === jobs.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(jobs.map((j) => j.id)));
    }
  };

  const handleDelete = async (jobId: string) => {
    if (!confirm("Delete this job and all its leads?")) return;
    try {
      await deleteJob(jobId);
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
      fetchJobs();
    } catch {
      // silently fail
    }
  };

  const handleBatchDelete = async () => {
    if (selected.size === 0) return;
    if (!confirm(`Delete ${selected.size} job(s) and all their leads?`)) return;
    setDeleting(true);
    try {
      await batchDeleteJobs(Array.from(selected));
      setSelected(new Set());
      fetchJobs();
    } catch {
      // silently fail
    } finally {
      setDeleting(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text)]">My Jobs</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {total} total job{total !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex gap-2">
          {selected.size > 0 && (
            <button
              className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-100"
              onClick={handleBatchDelete}
              disabled={deleting}
            >
              {deleting
                ? "Deleting..."
                : `Delete ${selected.size} selected`}
            </button>
          )}
          <Link href="/" className="btn-primary">
            New Scrape
          </Link>
        </div>
      </div>

      <div className="card overflow-hidden p-0">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="px-4 py-12 text-center text-[var(--text-secondary)]">
            No jobs yet.{" "}
            <Link href="/" className="text-primary-600 hover:underline">
              Start your first scrape
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--bg-secondary)]">
                  <th className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={jobs.length > 0 && selected.size === jobs.length}
                      onChange={toggleSelectAll}
                      className="h-4 w-4 rounded border-[var(--border)]"
                    />
                  </th>
                  <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                    Keyword
                  </th>
                  <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                    Location
                  </th>
                  <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                    Status
                  </th>
                  <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                    Layers
                  </th>
                  <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                    Leads
                  </th>
                  <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                    Created
                  </th>
                  <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    className={`border-b border-[var(--border)] transition-colors hover:bg-[var(--bg-secondary)] ${
                      selected.has(job.id) ? "bg-primary-50/50" : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selected.has(job.id)}
                        onChange={() => toggleSelect(job.id)}
                        className="h-4 w-4 rounded border-[var(--border)]"
                      />
                    </td>
                    <td className="px-4 py-3 font-medium text-[var(--text)]">
                      <Link
                        href={`/jobs/${job.id}`}
                        className="text-primary-600 hover:underline"
                      >
                        {job.keyword}
                      </Link>
                    </td>
                    <td className="max-w-[200px] truncate px-4 py-3 text-[var(--text-secondary)]">
                      {job.location}
                    </td>
                    <td className="px-4 py-3">{statusBadge(job.status)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5" title={`L1: ${job.layer1_status}, L2: ${job.layer2_status}, L3: ${job.layer3_status}`}>
                        <div className={`h-2.5 w-2.5 rounded-full ${layerDot(job.layer1_status)}`} />
                        <div className={`h-2.5 w-2.5 rounded-full ${layerDot(job.layer2_status)}`} />
                        <div className={`h-2.5 w-2.5 rounded-full ${layerDot(job.layer3_status)}`} />
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[var(--text)]">
                      {job.total_unique}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-[var(--text-secondary)]">
                      {new Date(job.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <Link
                          href={`/jobs/${job.id}`}
                          className="text-sm text-primary-600 hover:underline"
                        >
                          View
                        </Link>
                        <button
                          onClick={() => handleDelete(job.id)}
                          className="text-sm text-red-600 hover:underline"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-[var(--text-secondary)]">
            Page {page + 1} of {totalPages}
          </div>
          <div className="flex gap-2">
            <button
              className="btn-secondary"
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
            >
              Previous
            </button>
            <button
              className="btn-secondary"
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
