"use client";

import { useState } from "react";
import { JobCreatePayload } from "@/lib/api";

interface ScrapeFormProps {
  onSubmit: (payload: JobCreatePayload) => void;
  loading: boolean;
}

export default function ScrapeForm({ onSubmit, loading }: ScrapeFormProps) {
  const [locationType, setLocationType] = useState<JobCreatePayload["location_type"]>(
    "address"
  );
  const [location, setLocation] = useState("");
  const [keyword, setKeyword] = useState("");
  const [radiusKm, setRadiusKm] = useState(5);
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const payload: JobCreatePayload = {
      keyword: keyword.trim(),
      location:
        locationType === "coordinates"
          ? `${latitude}, ${longitude}`
          : location.trim(),
      location_type: locationType,
      radius_km: radiusKm,
      latitude: locationType === "coordinates" ? parseFloat(latitude) : null,
      longitude: locationType === "coordinates" ? parseFloat(longitude) : null,
    };

    onSubmit(payload);
  };

  const isValid =
    keyword.trim() &&
    (locationType === "address"
      ? location.trim()
      : latitude.trim() && longitude.trim());

  return (
    <form onSubmit={handleSubmit} className="card flex flex-col gap-5">
      <div>
        <label className="mb-1.5 block text-sm font-medium text-[var(--text)]">
          Location Type
        </label>
        <div className="flex gap-3">
          <button
            type="button"
            className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
              locationType === "address"
                ? "border-primary-500 bg-primary-50 text-primary-700"
                : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
            }`}
            onClick={() => setLocationType("address")}
          >
            Address / City
          </button>
          <button
            type="button"
            className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
              locationType === "coordinates"
                ? "border-primary-500 bg-primary-50 text-primary-700"
                : "border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
            }`}
            onClick={() => setLocationType("coordinates")}
          >
            Coordinates
          </button>
        </div>
      </div>

      {locationType === "address" ? (
        <div>
          <label
            htmlFor="location"
            className="mb-1.5 block text-sm font-medium text-[var(--text)]"
          >
            Location
          </label>
          <input
            id="location"
            type="text"
            className="input"
            placeholder="e.g., Austin, TX or 123 Main St, New York, NY"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label
              htmlFor="latitude"
              className="mb-1.5 block text-sm font-medium text-[var(--text)]"
            >
              Latitude
            </label>
            <input
              id="latitude"
              type="number"
              step="any"
              className="input"
              placeholder="30.2672"
              value={latitude}
              onChange={(e) => setLatitude(e.target.value)}
            />
          </div>
          <div>
            <label
              htmlFor="longitude"
              className="mb-1.5 block text-sm font-medium text-[var(--text)]"
            >
              Longitude
            </label>
            <input
              id="longitude"
              type="number"
              step="any"
              className="input"
              placeholder="-97.7431"
              value={longitude}
              onChange={(e) => setLongitude(e.target.value)}
            />
          </div>
        </div>
      )}

      <div>
        <label
          htmlFor="keyword"
          className="mb-1.5 block text-sm font-medium text-[var(--text)]"
        >
          Search Keyword
        </label>
        <input
          id="keyword"
          type="text"
          className="input"
          placeholder="e.g., restaurants, dentists, plumbers"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
      </div>

      <div>
        <label
          htmlFor="radius"
          className="mb-1.5 flex items-center justify-between text-sm font-medium text-[var(--text)]"
        >
          <span>Search Radius</span>
          <span className="text-primary-600">{radiusKm} km</span>
        </label>
        <input
          id="radius"
          type="range"
          min="1"
          max="50"
          step="1"
          className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-primary-200 accent-primary-600"
          value={radiusKm}
          onChange={(e) => setRadiusKm(parseInt(e.target.value, 10))}
        />
        <div className="mt-1 flex justify-between text-xs text-[var(--text-secondary)]">
          <span>1 km</span>
          <span>50 km</span>
        </div>
      </div>

      <button
        type="submit"
        className="btn-primary mt-1"
        disabled={!isValid || loading}
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            Starting Scrape...
          </span>
        ) : (
          "Start Scraping"
        )}
      </button>
    </form>
  );
}
