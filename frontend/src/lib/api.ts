const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface JobCreatePayload {
  keyword: string;
  location: string;
  location_type: "address" | "pincode" | "city" | "state" | "country" | "coordinates";
  radius_km: number;
  latitude?: number | null;
  longitude?: number | null;
}

export interface JobResponse {
  id: string;
  status: string;
  keyword: string;
  location: string;
  location_type: string;
  radius_km: number;
  latitude: number | null;
  longitude: number | null;
  progress: number;
  current_step: string | null;
  total_found: number;
  total_unique: number;
  places_api_calls: number;
  serp_api_calls: number;
  estimated_cost_usd: number;
  celery_task_id: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobListResponse {
  items: JobResponse[];
  total: number;
  skip: number;
  limit: number;
}

export interface LeadResponse {
  id: string;
  job_id: string;
  place_id: string;
  name: string;
  address: string | null;
  phone: string | null;
  website: string | null;
  rating: number | null;
  review_count: number | null;
  business_type: string | null;
  types: string[];
  latitude: number | null;
  longitude: number | null;
  opening_hours: Record<string, unknown> | null;
  photos: Record<string, unknown>[];
  price_level: number | null;
  business_status: string | null;
  maps_url: string | null;
  source: string;
  created_at: string;
}

export interface LeadListResponse {
  items: LeadResponse[];
  total: number;
  skip: number;
  limit: number;
}

export interface JobStatsResponse {
  job_id: string;
  total_leads: number;
  unique_place_ids: number;
  sources: Record<string, number>;
  avg_rating: number | null;
  with_phone: number;
  with_website: number;
  with_email: number;
  business_types: Record<string, number>;
}

export interface ResultsQueryParams {
  skip?: number;
  limit?: number;
  sort_by?: "name" | "rating" | "review_count" | "created_at";
  sort_order?: "asc" | "desc";
  search?: string;
  has_phone?: boolean;
  has_website?: boolean;
  min_rating?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function fetchApi<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_URL}${path}`;
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `API error: ${response.status}`);
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// Jobs API
// ---------------------------------------------------------------------------

export async function createJob(
  payload: JobCreatePayload
): Promise<JobResponse> {
  return fetchApi<JobResponse>("/api/jobs/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listJobs(
  skip = 0,
  limit = 50
): Promise<JobListResponse> {
  return fetchApi<JobListResponse>(
    `/api/jobs/?skip=${skip}&limit=${limit}`
  );
}

export async function getJob(jobId: string): Promise<JobResponse> {
  return fetchApi<JobResponse>(`/api/jobs/${jobId}`);
}

export async function cancelJob(jobId: string): Promise<JobResponse> {
  return fetchApi<JobResponse>(`/api/jobs/${jobId}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Results API
// ---------------------------------------------------------------------------

export async function getResults(
  jobId: string,
  params: ResultsQueryParams = {}
): Promise<LeadListResponse> {
  const searchParams = new URLSearchParams();
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined)
    searchParams.set("limit", String(params.limit));
  if (params.sort_by) searchParams.set("sort_by", params.sort_by);
  if (params.sort_order) searchParams.set("sort_order", params.sort_order);
  if (params.search) searchParams.set("search", params.search);
  if (params.has_phone !== undefined)
    searchParams.set("has_phone", String(params.has_phone));
  if (params.has_website !== undefined)
    searchParams.set("has_website", String(params.has_website));
  if (params.min_rating !== undefined)
    searchParams.set("min_rating", String(params.min_rating));

  const qs = searchParams.toString();
  return fetchApi<LeadListResponse>(
    `/api/results/${jobId}${qs ? `?${qs}` : ""}`
  );
}

export function getExportUrl(
  jobId: string,
  template: "default" | "clay" = "default"
): string {
  return `${API_URL}/api/results/${jobId}/export?template=${template}`;
}

export async function getJobStats(
  jobId: string
): Promise<JobStatsResponse> {
  return fetchApi<JobStatsResponse>(`/api/results/${jobId}/stats`);
}
