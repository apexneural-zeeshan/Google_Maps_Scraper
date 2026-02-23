"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import ScrapeForm from "@/components/ScrapeForm";
import { createJob, JobCreatePayload, JobResponse } from "@/lib/api";

export default function ScrapePage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (payload: JobCreatePayload) => {
    setError(null);
    setLoading(true);

    try {
      const job: JobResponse = await createJob(payload);
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-8">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-[var(--text)]">
          New Scrape Job
        </h1>
        <p className="mt-2 text-[var(--text-secondary)]">
          Extract business leads from Google Maps using Playwright + SerpAPI
        </p>
      </div>

      <div className="w-full max-w-xl">
        <ScrapeForm onSubmit={handleSubmit} loading={loading} />

        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}
      </div>

      <div className="grid w-full max-w-3xl grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="card text-center">
          <div className="text-2xl font-bold text-primary-600">Layer 1</div>
          <div className="mt-1 text-sm text-[var(--text-secondary)]">
            Playwright
          </div>
          <div className="mt-2 text-xs text-[var(--text-secondary)]">
            Headless browser scraping — free, unlimited
          </div>
        </div>
        <div className="card text-center">
          <div className="text-2xl font-bold text-primary-600">Layer 2</div>
          <div className="mt-1 text-sm text-[var(--text-secondary)]">
            SerpAPI
          </div>
          <div className="mt-2 text-xs text-[var(--text-secondary)]">
            Validation &amp; supplementary results
          </div>
        </div>
        <div className="card text-center">
          <div className="text-2xl font-bold text-primary-600">Layer 3</div>
          <div className="mt-1 text-sm text-[var(--text-secondary)]">
            Outscraper
          </div>
          <div className="mt-2 text-xs text-[var(--text-secondary)]">
            Email &amp; social enrichment (optional)
          </div>
        </div>
      </div>
    </div>
  );
}
