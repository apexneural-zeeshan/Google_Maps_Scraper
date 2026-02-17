"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import JobStatusComponent from "@/components/JobStatus";
import ResultsTable from "@/components/ResultsTable";
import { getJob, getResults, JobResponse, LeadResponse } from "@/lib/api";

export default function JobDetailPage() {
  const params = useParams();
  const jobId = params.id as string;

  const [job, setJob] = useState<JobResponse | null>(null);
  const [leads, setLeads] = useState<LeadResponse[]>([]);
  const [totalLeads, setTotalLeads] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 50;

  const fetchJob = useCallback(async () => {
    try {
      const data = await getJob(jobId);
      setJob(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load job");
    }
  }, [jobId]);

  const fetchResults = useCallback(async () => {
    try {
      const data = await getResults(jobId, {
        skip: page * pageSize,
        limit: pageSize,
      });
      setLeads(data.items);
      setTotalLeads(data.total);
    } catch {
      // Results may not be available yet — that's OK
    }
  }, [jobId, page]);

  // Poll job status
  useEffect(() => {
    fetchJob();
    const interval = setInterval(() => {
      fetchJob();
    }, 2000);
    return () => clearInterval(interval);
  }, [fetchJob]);

  // Fetch results when job progresses or page changes
  useEffect(() => {
    if (job && job.total_unique > 0) {
      fetchResults();
    }
  }, [job?.total_unique, page, fetchResults]);

  // Stop polling when job is done
  useEffect(() => {
    if (
      job &&
      (job.status === "completed" ||
        job.status === "failed" ||
        job.status === "cancelled")
    ) {
      fetchResults();
    }
  }, [job?.status, fetchResults]);

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-700">
        <h2 className="font-semibold">Error</h2>
        <p className="mt-1 text-sm">{error}</p>
        <Link href="/" className="btn-primary mt-4 inline-block">
          Back to Home
        </Link>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
      </div>
    );
  }

  const totalPages = Math.ceil(totalLeads / pageSize);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <Link
            href="/"
            className="text-sm text-[var(--text-secondary)] hover:text-[var(--text)]"
          >
            &larr; Back
          </Link>
          <h1 className="mt-1 text-2xl font-bold text-[var(--text)]">
            {job.keyword} in {job.location}
          </h1>
        </div>
        <div className="text-right text-sm text-[var(--text-secondary)]">
          <div>Created {new Date(job.created_at).toLocaleString()}</div>
          <div>Radius: {job.radius_km} km</div>
        </div>
      </div>

      <JobStatusComponent job={job} />

      {leads.length > 0 && (
        <>
          <ResultsTable leads={leads} jobId={jobId} />

          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <div className="text-sm text-[var(--text-secondary)]">
                Showing {page * pageSize + 1}–
                {Math.min((page + 1) * pageSize, totalLeads)} of {totalLeads}
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
                  onClick={() =>
                    setPage(Math.min(totalPages - 1, page + 1))
                  }
                  disabled={page >= totalPages - 1}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
