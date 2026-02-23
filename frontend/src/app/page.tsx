"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getOverviewStats,
  getApiUsage,
  getRecentActivity,
  listJobs,
  OverviewStats,
  ApiUsage,
  RecentActivityItem,
  JobResponse,
} from "@/lib/api";

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="card flex flex-col items-center justify-center py-5">
      <div className="text-3xl font-bold text-primary-600">{value}</div>
      <div className="mt-1 text-sm font-medium text-[var(--text)]">{label}</div>
      {sub && (
        <div className="mt-0.5 text-xs text-[var(--text-secondary)]">{sub}</div>
      )}
    </div>
  );
}

function UsageBar({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number | string;
}) {
  const numLimit = typeof limit === "string" ? Infinity : limit;
  const pct = numLimit === Infinity ? 0 : Math.min((used / numLimit) * 100, 100);
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-[var(--text)]">{label}</span>
        <span className="text-[var(--text-secondary)]">
          {used} / {typeof limit === "string" ? limit : limit.toLocaleString()}
        </span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--bg-secondary)]">
        <div
          className={`h-full rounded-full transition-all ${
            pct > 80 ? "bg-red-500" : pct > 50 ? "bg-yellow-500" : "bg-primary-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    completed: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    running: "bg-blue-100 text-blue-700",
    pending: "bg-yellow-100 text-yellow-700",
    cancelled: "bg-gray-100 text-gray-600",
  };
  return map[status] || "bg-gray-100 text-gray-600";
}

export default function DashboardPage() {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [usage, setUsage] = useState<ApiUsage | null>(null);
  const [activity, setActivity] = useState<RecentActivityItem[]>([]);
  const [recentJobs, setRecentJobs] = useState<JobResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [s, u, a, j] = await Promise.all([
          getOverviewStats(),
          getApiUsage(),
          getRecentActivity(),
          listJobs(0, 5),
        ]);
        setStats(s);
        setUsage(u);
        setActivity(a);
        setRecentJobs(j.items);
      } catch {
        // Stats may not be available if backend is down
      } finally {
        setLoading(false);
      }
    }
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[var(--text)]">Dashboard</h1>
          <p className="mt-1 text-[var(--text-secondary)]">
            Google Maps lead scraping overview
          </p>
        </div>
        <div className="flex gap-3">
          <Link href="/scrape" className="btn-primary">
            New Scrape
          </Link>
          <Link href="/batch" className="btn-secondary">
            Batch Scrape
          </Link>
        </div>
      </div>

      {/* Stat Cards */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard
            label="Total Leads"
            value={stats.total_leads.toLocaleString()}
            sub={`${stats.total_unique_leads.toLocaleString()} unique`}
          />
          <StatCard
            label="Active Jobs"
            value={stats.running_jobs}
            sub={`${stats.total_jobs} total`}
          />
          <StatCard
            label="Success Rate"
            value={`${stats.success_rate.toFixed(0)}%`}
            sub={`${stats.completed_jobs} completed`}
          />
          <StatCard
            label="Favorites"
            value={stats.favorite_leads}
            sub={`of ${stats.total_leads} leads`}
          />
        </div>
      )}

      {/* Two-column: Recent Jobs + API Usage */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent Jobs */}
        <div className="card">
          <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
            <h2 className="text-lg font-semibold text-[var(--text)]">
              Recent Jobs
            </h2>
            <Link
              href="/jobs"
              className="text-sm text-primary-600 hover:underline"
            >
              View all
            </Link>
          </div>
          {recentJobs.length === 0 ? (
            <p className="py-6 text-center text-sm text-[var(--text-secondary)]">
              No jobs yet. Start your first scrape!
            </p>
          ) : (
            <div className="divide-y divide-[var(--border)]">
              {recentJobs.map((job) => (
                <Link
                  key={job.id}
                  href={`/jobs/${job.id}`}
                  className="flex items-center justify-between py-3 transition-colors hover:bg-[var(--bg-secondary)]"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-[var(--text)]">
                      {job.keyword} in {job.location}
                    </div>
                    <div className="text-xs text-[var(--text-secondary)]">
                      {new Date(job.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="ml-3 flex items-center gap-3">
                    <span className="text-sm font-medium text-[var(--text-secondary)]">
                      {job.total_unique} leads
                    </span>
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusBadge(job.status)}`}
                    >
                      {job.status}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* API Usage */}
        <div className="card">
          <h2 className="border-b border-[var(--border)] pb-3 text-lg font-semibold text-[var(--text)]">
            API Usage — {usage?.month || "N/A"}
          </h2>
          {usage ? (
            <div className="mt-4 flex flex-col gap-4">
              <UsageBar
                label="SerpAPI"
                used={usage.serpapi.used}
                limit={usage.serpapi.limit}
              />
              <UsageBar
                label="Outscraper"
                used={usage.outscraper.used}
                limit={usage.outscraper.limit}
              />
              <UsageBar
                label="Playwright Pages"
                used={usage.playwright.total_pages_scraped}
                limit={usage.playwright.limit}
              />
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-[var(--text-secondary)]">
              Usage data unavailable.
            </p>
          )}
        </div>
      </div>

      {/* Recent Activity */}
      {activity.length > 0 && (
        <div className="card">
          <h2 className="border-b border-[var(--border)] pb-3 text-lg font-semibold text-[var(--text)]">
            Recent Activity
          </h2>
          <div className="divide-y divide-[var(--border)]">
            {activity.map((item, i) => (
              <div key={i} className="flex items-center justify-between py-3">
                <div className="flex items-center gap-3">
                  <div
                    className={`h-2 w-2 rounded-full ${
                      item.type === "completed"
                        ? "bg-green-500"
                        : item.type === "failed"
                          ? "bg-red-500"
                          : "bg-blue-500"
                    }`}
                  />
                  <div>
                    <span className="text-sm font-medium text-[var(--text)]">
                      {item.keyword} in {item.location}
                    </span>
                    {item.leads !== undefined && (
                      <span className="ml-2 text-xs text-[var(--text-secondary)]">
                        {item.leads} leads
                      </span>
                    )}
                    {item.error && (
                      <span className="ml-2 text-xs text-red-600">
                        {item.error}
                      </span>
                    )}
                  </div>
                </div>
                <span className="text-xs text-[var(--text-secondary)]">
                  {item.time}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
