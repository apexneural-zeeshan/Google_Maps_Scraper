"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createBatch, BatchJobInput } from "@/lib/api";

interface JobRow {
  id: string;
  keyword: string;
  location: string;
  location_type: string;
  radius_km: number;
}

function newRow(): JobRow {
  return {
    id: crypto.randomUUID(),
    keyword: "",
    location: "",
    location_type: "city",
    radius_km: 5,
  };
}

export default function BatchCreatePage() {
  const router = useRouter();
  const [batchName, setBatchName] = useState("");
  const [userEmail, setUserEmail] = useState("");
  const [rows, setRows] = useState<JobRow[]>([newRow(), newRow(), newRow()]);
  const [csvText, setCsvText] = useState("");
  const [mode, setMode] = useState<"form" | "csv">("form");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [csvPreview, setCsvPreview] = useState<BatchJobInput[]>([]);

  const addRow = () => setRows((prev) => [...prev, newRow()]);

  const removeRow = (id: string) => {
    setRows((prev) => (prev.length > 1 ? prev.filter((r) => r.id !== id) : prev));
  };

  const updateRow = (id: string, field: keyof JobRow, value: string | number) => {
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, [field]: value } : r))
    );
  };

  const parseCsv = useCallback((text: string) => {
    const lines = text
      .trim()
      .split("\n")
      .filter((l) => l.trim());
    if (lines.length === 0) {
      setCsvPreview([]);
      return;
    }

    // Check if first line is a header
    const firstLine = lines[0].toLowerCase();
    const startIdx = firstLine.includes("keyword") ? 1 : 0;

    const parsed: BatchJobInput[] = [];
    for (let i = startIdx; i < lines.length; i++) {
      const parts = lines[i].split(",").map((p) => p.trim());
      if (parts.length >= 2) {
        parsed.push({
          keyword: parts[0],
          location: parts[1],
          location_type: parts[2] || "city",
          radius_km: parts[3] ? parseFloat(parts[3]) : 5,
        });
      }
    }
    setCsvPreview(parsed);
  }, []);

  const handleCsvChange = (text: string) => {
    setCsvText(text);
    parseCsv(text);
  };

  const handleCsvUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setCsvText(text);
      parseCsv(text);
    };
    reader.readAsText(file);
  };

  const getJobInputs = (): BatchJobInput[] => {
    if (mode === "csv") return csvPreview;
    return rows
      .filter((r) => r.keyword.trim() && r.location.trim())
      .map((r) => ({
        keyword: r.keyword.trim(),
        location: r.location.trim(),
        location_type: r.location_type,
        radius_km: r.radius_km,
      }));
  };

  const jobInputs = getJobInputs();
  const estimatedHours = (jobInputs.length * 3) / 60; // ~3 min per job

  const handleSubmit = async () => {
    if (jobInputs.length === 0) return;
    setError(null);
    setLoading(true);

    try {
      const result = await createBatch({
        name: batchName.trim() || null,
        user_email: userEmail.trim() || null,
        jobs: jobInputs,
      });
      router.push(`/batch/${result.batch.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create batch");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text)]">Batch Scrape</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Submit multiple scraping jobs to process sequentially overnight.
        </p>
      </div>

      {/* Batch Info */}
      <div className="card flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label
              htmlFor="batch-name"
              className="mb-1.5 block text-sm font-medium text-[var(--text)]"
            >
              Batch Name <span className="text-[var(--text-secondary)]">(optional)</span>
            </label>
            <input
              id="batch-name"
              type="text"
              className="input"
              placeholder="e.g., Overnight India Scrape"
              value={batchName}
              onChange={(e) => setBatchName(e.target.value)}
            />
          </div>
          <div>
            <label
              htmlFor="batch-email"
              className="mb-1.5 block text-sm font-medium text-[var(--text)]"
            >
              Notification Email <span className="text-[var(--text-secondary)]">(optional)</span>
            </label>
            <input
              id="batch-email"
              type="email"
              className="input"
              placeholder="your@email.com — notified when done"
              value={userEmail}
              onChange={(e) => setUserEmail(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-3">
        <button
          type="button"
          className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
            mode === "form"
              ? "border-primary-500 bg-primary-50 text-primary-700"
              : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
          }`}
          onClick={() => setMode("form")}
        >
          Form Input
        </button>
        <button
          type="button"
          className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
            mode === "csv"
              ? "border-primary-500 bg-primary-50 text-primary-700"
              : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
          }`}
          onClick={() => setMode("csv")}
        >
          CSV Paste / Upload
        </button>
      </div>

      {/* Form Mode */}
      {mode === "form" && (
        <div className="card flex flex-col gap-3">
          {rows.map((row, idx) => (
            <div key={row.id} className="flex items-end gap-2">
              <div className="w-6 shrink-0 text-center text-xs text-[var(--text-secondary)]">
                {idx + 1}
              </div>
              <div className="flex-1">
                {idx === 0 && (
                  <label className="mb-1 block text-xs text-[var(--text-secondary)]">
                    Keyword
                  </label>
                )}
                <input
                  type="text"
                  className="input"
                  placeholder="restaurants"
                  value={row.keyword}
                  onChange={(e) => updateRow(row.id, "keyword", e.target.value)}
                />
              </div>
              <div className="flex-1">
                {idx === 0 && (
                  <label className="mb-1 block text-xs text-[var(--text-secondary)]">
                    Location
                  </label>
                )}
                <input
                  type="text"
                  className="input"
                  placeholder="Hyderabad"
                  value={row.location}
                  onChange={(e) => updateRow(row.id, "location", e.target.value)}
                />
              </div>
              <div className="w-28 shrink-0">
                {idx === 0 && (
                  <label className="mb-1 block text-xs text-[var(--text-secondary)]">
                    Type
                  </label>
                )}
                <select
                  className="input"
                  value={row.location_type}
                  onChange={(e) =>
                    updateRow(row.id, "location_type", e.target.value)
                  }
                >
                  <option value="city">City</option>
                  <option value="address">Address</option>
                  <option value="state">State</option>
                  <option value="country">Country</option>
                  <option value="pincode">Pincode</option>
                </select>
              </div>
              <div className="w-20 shrink-0">
                {idx === 0 && (
                  <label className="mb-1 block text-xs text-[var(--text-secondary)]">
                    Radius
                  </label>
                )}
                <input
                  type="number"
                  className="input"
                  min="1"
                  max="50"
                  value={row.radius_km}
                  onChange={(e) =>
                    updateRow(row.id, "radius_km", parseInt(e.target.value, 10) || 5)
                  }
                />
              </div>
              <button
                type="button"
                className="mb-0.5 shrink-0 rounded p-1.5 text-sm text-red-500 hover:bg-red-50"
                onClick={() => removeRow(row.id)}
                title="Remove row"
              >
                &times;
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn-secondary self-start text-sm"
            onClick={addRow}
          >
            + Add Another
          </button>
        </div>
      )}

      {/* CSV Mode */}
      {mode === "csv" && (
        <div className="card flex flex-col gap-4">
          <div>
            <label
              htmlFor="csv-input"
              className="mb-1.5 block text-sm font-medium text-[var(--text)]"
            >
              Paste CSV
            </label>
            <textarea
              id="csv-input"
              className="input min-h-[120px] font-mono text-sm"
              placeholder={"keyword,location,location_type,radius_km\nrestaurants,Hyderabad,city,5\ncafes,Bangalore,city,5"}
              value={csvText}
              onChange={(e) => handleCsvChange(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--text-secondary)]">or</span>
            <label className="btn-secondary cursor-pointer text-sm">
              Upload .csv
              <input
                type="file"
                accept=".csv,.txt"
                className="hidden"
                onChange={handleCsvUpload}
              />
            </label>
          </div>
          {csvPreview.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium text-[var(--text)]">
                Preview ({csvPreview.length} jobs)
              </p>
              <div className="overflow-x-auto rounded border border-[var(--border)]">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="bg-[var(--bg-secondary)]">
                      <th className="px-3 py-2 text-xs text-[var(--text-secondary)]">#</th>
                      <th className="px-3 py-2 text-xs text-[var(--text-secondary)]">Keyword</th>
                      <th className="px-3 py-2 text-xs text-[var(--text-secondary)]">Location</th>
                      <th className="px-3 py-2 text-xs text-[var(--text-secondary)]">Type</th>
                      <th className="px-3 py-2 text-xs text-[var(--text-secondary)]">Radius</th>
                    </tr>
                  </thead>
                  <tbody>
                    {csvPreview.slice(0, 20).map((job, i) => (
                      <tr key={i} className="border-t border-[var(--border)]">
                        <td className="px-3 py-1.5 text-[var(--text-secondary)]">{i + 1}</td>
                        <td className="px-3 py-1.5">{job.keyword}</td>
                        <td className="px-3 py-1.5">{job.location}</td>
                        <td className="px-3 py-1.5">{job.location_type}</td>
                        <td className="px-3 py-1.5">{job.radius_km} km</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {csvPreview.length > 20 && (
                  <p className="px-3 py-2 text-xs text-[var(--text-secondary)]">
                    ...and {csvPreview.length - 20} more
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Summary & Submit */}
      <div className="card flex items-center justify-between">
        <div className="text-sm text-[var(--text-secondary)]">
          {jobInputs.length > 0 ? (
            <>
              <span className="font-semibold text-[var(--text)]">{jobInputs.length}</span> job
              {jobInputs.length !== 1 ? "s" : ""} &middot; Est.{" "}
              {estimatedHours < 1
                ? `~${Math.ceil(estimatedHours * 60)} min`
                : `~${estimatedHours.toFixed(1)} hours`}
            </>
          ) : (
            "Add at least one job to start"
          )}
        </div>
        <button
          type="button"
          className="btn-primary"
          disabled={jobInputs.length === 0 || loading}
          onClick={handleSubmit}
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Starting Batch...
            </span>
          ) : (
            `Start Batch (${jobInputs.length} jobs)`
          )}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
