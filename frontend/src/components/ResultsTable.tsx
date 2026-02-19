"use client";

import { useState } from "react";
import { LeadResponse, getExportUrl } from "@/lib/api";

interface ResultsTableProps {
  leads: LeadResponse[];
  jobId: string;
}

type SortKey = "name" | "rating" | "review_count";

export default function ResultsTable({ leads, jobId }: ResultsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortAsc, setSortAsc] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

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
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
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

  // Filter
  const filtered = leads.filter(
    (l) =>
      !search ||
      l.name.toLowerCase().includes(search.toLowerCase()) ||
      (l.address && l.address.toLowerCase().includes(search.toLowerCase()))
  );

  // Sort (local sort for current page)
  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    if (sortKey === "name") {
      cmp = a.name.localeCompare(b.name);
    } else if (sortKey === "rating") {
      cmp = (a.rating ?? 0) - (b.rating ?? 0);
    } else if (sortKey === "review_count") {
      cmp = (a.review_count ?? 0) - (b.review_count ?? 0);
    }
    return sortAsc ? cmp : -cmp;
  });

  const sortIcon = (key: SortKey) => {
    if (sortKey !== key) return "\u2195";
    return sortAsc ? "\u2191" : "\u2193";
  };

  return (
    <div className="card overflow-hidden p-0">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] p-4">
        <input
          type="text"
          className="input max-w-xs"
          placeholder="Search results..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="flex gap-2">
          <a
            href={getExportUrl(jobId, "default")}
            className="btn-secondary inline-flex items-center gap-1.5"
            download
          >
            Export CSV
          </a>
          <a
            href={getExportUrl(jobId, "clay")}
            className="btn-secondary inline-flex items-center gap-1.5"
            download
          >
            Export (Clay)
          </a>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] bg-[var(--bg-secondary)]">
              <th className="px-4 py-3">
                <input
                  type="checkbox"
                  title="Select all"
                  checked={
                    filtered.length > 0 && selected.size === filtered.length
                  }
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-[var(--border)]"
                />
              </th>
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
              <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                Owner
              </th>
              <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                Employees
              </th>
              <th className="px-4 py-3 font-medium text-[var(--text-secondary)]">
                Founded
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
                    <span className="text-[var(--text-secondary)]">
                      {"\u2014"}
                    </span>
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
                      {new URL(lead.website).hostname}
                    </a>
                  ) : (
                    <span className="text-[var(--text-secondary)]">
                      {"\u2014"}
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-[var(--text-secondary)]">
                  {lead.owner_name || "\u2014"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-[var(--text-secondary)]">
                  {lead.employee_count || "\u2014"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-[var(--text-secondary)]">
                  {lead.year_established || "\u2014"}
                </td>
                <td className="px-4 py-3">
                  {lead.rating ? (
                    <span className="inline-flex items-center gap-1">
                      <span className="text-yellow-500">{"\u2605"}</span>
                      {lead.rating.toFixed(1)}
                    </span>
                  ) : (
                    <span className="text-[var(--text-secondary)]">
                      {"\u2014"}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  {lead.review_count?.toLocaleString() ?? "\u2014"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                      lead.source.includes("places_api")
                        ? "bg-blue-100 text-blue-700"
                        : lead.source.includes("serp_api")
                          ? "bg-green-100 text-green-700"
                          : "bg-purple-100 text-purple-700"
                    }`}
                  >
                    {lead.source}
                  </span>
                </td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td
                  colSpan={12}
                  className="px-4 py-8 text-center text-[var(--text-secondary)]"
                >
                  {search
                    ? "No results match your search."
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
