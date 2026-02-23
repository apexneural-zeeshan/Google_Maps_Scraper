"use client";

import { useState, useCallback } from "react";
import {
  LeadResponse,
  LeadUpdate,
  getExportUrl,
  updateLead,
  deleteLead,
  batchUpdateLeads,
  batchDeleteLeads,
} from "@/lib/api";

interface ResultsTableProps {
  leads: LeadResponse[];
  jobId: string;
  onRefresh: () => void;
}

type SortKey = "name" | "rating" | "review_count";

export default function ResultsTable({
  leads,
  jobId,
  onRefresh,
}: ResultsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortAsc, setSortAsc] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filterPhone, setFilterPhone] = useState(false);
  const [filterWebsite, setFilterWebsite] = useState(false);
  const [filterFavorite, setFilterFavorite] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [bulkLoading, setBulkLoading] = useState(false);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === filtered.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map((l) => l.id)));
    }
  };

  const handleToggleFavorite = useCallback(
    async (lead: LeadResponse) => {
      try {
        await updateLead(lead.id, { is_favorite: !lead.is_favorite });
        onRefresh();
      } catch {
        // silent
      }
    },
    [onRefresh]
  );

  const handleBulkFavorite = async () => {
    if (selected.size === 0) return;
    setBulkLoading(true);
    try {
      await batchUpdateLeads(Array.from(selected), { is_favorite: true });
      setSelected(new Set());
      onRefresh();
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkArchive = async () => {
    if (selected.size === 0) return;
    setBulkLoading(true);
    try {
      await batchUpdateLeads(Array.from(selected), { is_archived: true });
      setSelected(new Set());
      onRefresh();
    } finally {
      setBulkLoading(false);
    }
  };

  const handleBulkDelete = async () => {
    if (selected.size === 0) return;
    if (!confirm(`Delete ${selected.size} lead(s)? This cannot be undone.`))
      return;
    setBulkLoading(true);
    try {
      await batchDeleteLeads(Array.from(selected));
      setSelected(new Set());
      onRefresh();
    } finally {
      setBulkLoading(false);
    }
  };

  const handleDeleteLead = async (leadId: string) => {
    if (!confirm("Delete this lead?")) return;
    try {
      await deleteLead(leadId);
      onRefresh();
    } catch {
      // silent
    }
  };

  // Filter
  const filtered = leads.filter((l) => {
    if (search) {
      const q = search.toLowerCase();
      const matches =
        l.name.toLowerCase().includes(q) ||
        (l.address && l.address.toLowerCase().includes(q)) ||
        (l.phone && l.phone.includes(q)) ||
        (l.primary_email && l.primary_email.toLowerCase().includes(q));
      if (!matches) return false;
    }
    if (filterPhone && !l.phone) return false;
    if (filterWebsite && !l.website) return false;
    if (filterFavorite && !l.is_favorite) return false;
    return true;
  });

  // Sort
  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    if (sortKey === "name") cmp = a.name.localeCompare(b.name);
    else if (sortKey === "rating") cmp = (a.rating ?? 0) - (b.rating ?? 0);
    else if (sortKey === "review_count")
      cmp = (a.review_count ?? 0) - (b.review_count ?? 0);
    return sortAsc ? cmp : -cmp;
  });

  const sortIcon = (key: SortKey) => {
    if (sortKey !== key) return "\u2195";
    return sortAsc ? "\u2191" : "\u2193";
  };

  const exportOptions = [
    { label: "CSV (Default)", format: "csv" as const, template: "default" as const },
    { label: "CSV (Clay)", format: "csv" as const, template: "clay" as const },
    { label: "CSV (HubSpot)", format: "csv" as const, template: "hubspot" as const },
    { label: "CSV (Outreach)", format: "csv" as const, template: "outreach" as const },
    { label: "Excel (Default)", format: "xlsx" as const, template: "default" as const },
    { label: "Excel (Clay)", format: "xlsx" as const, template: "clay" as const },
  ];

  return (
    <div className="card overflow-hidden p-0">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] p-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            className="input max-w-xs"
            placeholder="Search leads..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {/* Filter toggles */}
          <button
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filterPhone
                ? "bg-primary-100 text-primary-700"
                : "bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:bg-[var(--border)]"
            }`}
            onClick={() => setFilterPhone(!filterPhone)}
          >
            Has Phone
          </button>
          <button
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filterWebsite
                ? "bg-primary-100 text-primary-700"
                : "bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:bg-[var(--border)]"
            }`}
            onClick={() => setFilterWebsite(!filterWebsite)}
          >
            Has Website
          </button>
          <button
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filterFavorite
                ? "bg-yellow-100 text-yellow-700"
                : "bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:bg-[var(--border)]"
            }`}
            onClick={() => setFilterFavorite(!filterFavorite)}
          >
            Favorites
          </button>
        </div>

        {/* Export dropdown */}
        <div className="relative">
          <button
            className="btn-secondary inline-flex items-center gap-1.5"
            onClick={() => setExportOpen(!exportOpen)}
          >
            Export
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {exportOpen && (
            <div className="absolute right-0 z-10 mt-1 w-48 rounded-lg border border-[var(--border)] bg-[var(--card-bg)] py-1 shadow-lg">
              {exportOptions.map((opt) => (
                <a
                  key={`${opt.format}-${opt.template}`}
                  href={getExportUrl(jobId, opt.format, opt.template)}
                  download
                  className="block px-4 py-2 text-sm text-[var(--text)] hover:bg-[var(--bg-secondary)]"
                  onClick={() => setExportOpen(false)}
                >
                  {opt.label}
                </a>
              ))}
              <hr className="my-1 border-[var(--border)]" />
              <a
                href={getExportUrl(jobId, "csv", "default", true)}
                download
                className="block px-4 py-2 text-sm text-yellow-700 hover:bg-[var(--bg-secondary)]"
                onClick={() => setExportOpen(false)}
              >
                Favorites Only (CSV)
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Bulk Actions Bar */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 border-b border-[var(--border)] bg-primary-50/50 px-4 py-2">
          <span className="text-sm font-medium text-primary-700">
            {selected.size} selected
          </span>
          <button
            className="rounded px-2 py-1 text-xs font-medium text-yellow-700 hover:bg-yellow-100"
            onClick={handleBulkFavorite}
            disabled={bulkLoading}
          >
            Favorite
          </button>
          <button
            className="rounded px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
            onClick={handleBulkArchive}
            disabled={bulkLoading}
          >
            Archive
          </button>
          <button
            className="rounded px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
            onClick={handleBulkDelete}
            disabled={bulkLoading}
          >
            Delete
          </button>
          <button
            className="ml-auto text-xs text-[var(--text-secondary)] hover:text-[var(--text)]"
            onClick={() => setSelected(new Set())}
          >
            Clear selection
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] bg-[var(--bg-secondary)]">
              <th className="px-4 py-3">
                <input
                  type="checkbox"
                  title="Select all"
                  checked={filtered.length > 0 && selected.size === filtered.length}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-[var(--border)]"
                />
              </th>
              <th className="w-8 px-2 py-3"></th>
              <th
                className="cursor-pointer px-4 py-3 font-medium text-[var(--text-secondary)] hover:text-[var(--text)]"
                onClick={() => handleSort("name")}
              >
                Name {sortIcon("name")}
              </th>
              <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                Address
              </th>
              <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                Phone
              </th>
              <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                Email
              </th>
              <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                Website
              </th>
              <th
                className="cursor-pointer px-4 py-3 font-medium text-[var(--text-secondary)] hover:text-[var(--text)]"
                onClick={() => handleSort("rating")}
              >
                Rating {sortIcon("rating")}
              </th>
              <th
                className="cursor-pointer px-4 py-3 font-medium text-[var(--text-secondary)] hover:text-[var(--text)]"
                onClick={() => handleSort("review_count")}
              >
                Reviews {sortIcon("review_count")}
              </th>
              <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                Source
              </th>
              <th className="w-8 px-2 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((lead) => (
              <tr
                key={lead.id}
                className={`border-b border-[var(--border)] transition-colors hover:bg-[var(--bg-secondary)] ${
                  selected.has(lead.id) ? "bg-primary-50/50" : ""
                }`}
              >
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    title={`Select ${lead.name}`}
                    checked={selected.has(lead.id)}
                    onChange={() => toggleSelect(lead.id)}
                    className="h-4 w-4 rounded border-[var(--border)]"
                  />
                </td>
                <td className="px-2 py-3">
                  <button
                    title={lead.is_favorite ? "Unfavorite" : "Favorite"}
                    onClick={() => handleToggleFavorite(lead)}
                    className="text-lg leading-none transition-colors hover:scale-110"
                  >
                    {lead.is_favorite ? (
                      <span className="text-yellow-500">{"\u2605"}</span>
                    ) : (
                      <span className="text-gray-300 hover:text-yellow-400">{"\u2606"}</span>
                    )}
                  </button>
                </td>
                <td className="max-w-[200px] truncate px-4 py-3 font-medium text-[var(--text)]">
                  {lead.maps_url ? (
                    <a
                      href={lead.maps_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 hover:underline"
                    >
                      {lead.name}
                    </a>
                  ) : (
                    lead.name
                  )}
                </td>
                <td className="max-w-[200px] truncate px-4 py-3 text-[var(--text-secondary)]">
                  {lead.address || "\u2014"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-[var(--text-secondary)]">
                  {lead.phone || "\u2014"}
                </td>
                <td className="max-w-[200px] truncate px-4 py-3">
                  {lead.primary_email ? (
                    <a
                      href={`mailto:${lead.primary_email}`}
                      className="text-primary-600 hover:underline"
                    >
                      {lead.primary_email}
                    </a>
                  ) : (
                    <span className="text-[var(--text-secondary)]">{"\u2014"}</span>
                  )}
                </td>
                <td className="max-w-[150px] truncate px-4 py-3">
                  {lead.website ? (
                    <a
                      href={lead.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 hover:underline"
                    >
                      {(() => {
                        try {
                          return new URL(lead.website).hostname;
                        } catch {
                          return lead.website;
                        }
                      })()}
                    </a>
                  ) : (
                    <span className="text-[var(--text-secondary)]">{"\u2014"}</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {lead.rating ? (
                    <span className="inline-flex items-center gap-1">
                      <span className="text-yellow-500">{"\u2605"}</span>
                      {lead.rating.toFixed(1)}
                    </span>
                  ) : (
                    <span className="text-[var(--text-secondary)]">{"\u2014"}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  {lead.review_count?.toLocaleString() ?? "\u2014"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                      lead.source.includes("playwright")
                        ? "bg-purple-100 text-purple-700"
                        : lead.source.includes("serp")
                          ? "bg-green-100 text-green-700"
                          : "bg-blue-100 text-blue-700"
                    }`}
                  >
                    {lead.source}
                  </span>
                </td>
                <td className="px-2 py-3">
                  <button
                    title="Delete lead"
                    onClick={() => handleDeleteLead(lead.id)}
                    className="text-gray-400 transition-colors hover:text-red-500"
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td
                  colSpan={11}
                  className="px-4 py-8 text-center text-[var(--text-secondary)]"
                >
                  {search || filterPhone || filterWebsite || filterFavorite
                    ? "No results match your filters."
                    : "No results yet."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
