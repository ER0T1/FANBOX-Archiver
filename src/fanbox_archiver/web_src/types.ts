namespace FanboxUI {
  export type JobStatus =
    | "queued" | "running" | "cancelling" | "completed"
    | "failed" | "cancelled" | "interrupted";

  export interface Page<T> {
    items: T[];
    page: number;
    page_size: number;
    total: number;
    pages: number;
  }

  export interface PostSummary {
    post_id: string;
    creator_id: string;
    creator_name: string;
    title: string;
    published_at: string | null;
    updated_at: string | null;
    status: string;
    version_count: number;
    latest_version: number | null;
    cover_url: string | null;
    fee_required: number | null;
    is_pinned: boolean;
    tags: string[];
  }

  export interface PostNeighbor {
    post_id: string;
    creator_id: string;
    creator_name: string;
    title: string;
    published_at: string | null;
    is_pinned: boolean;
  }

  export interface PostNavigation {
    previous: PostNeighbor | null;
    next: PostNeighbor | null;
    position: number | null;
    total: number;
  }

  export interface ArchiveVersion {
    number: number;
    captured_at: string;
    remote_updated_at?: string | null;
    status: string;
  }

  export interface ContentBlock {
    type: string;
    text?: string | null;
    asset_id?: string | null;
    url?: string | null;
    name?: string | null;
    level?: number | null;
    media_url?: string;
    media_type?: string;
    filename?: string;
    styles?: Array<{type: "bold"; offset: number; length: number}>;
    embed?: Record<string, unknown> | null;
  }

  export interface PostDetail {
    post_id: string;
    creator_id: string;
    creator_name: string;
    title: string;
    published_at: string | null;
    updated_at: string | null;
    url: string;
    fee_required: number | null;
    is_pinned: boolean;
    version: number;
    versions: ArchiveVersion[];
    cover_url: string | null;
    blocks: ContentBlock[];
    navigation: PostNavigation;
  }

  export interface CreatorSummary {
    creator_id: string;
    name: string;
    post_count: number;
    completed_count: number;
    fancard_count?: number;
    status: string;
    avatar_url: string | null;
    profile_available: boolean;
  }

  export interface FanCardSelection {
    type: "fancard";
    creatorId: string;
    month: string;
  }

  export interface WebJob {
    job_id: string;
    kind: "backup" | "verify";
    status: JobStatus;
    created_at: string;
    started_at?: string | null;
    finished_at?: string | null;
    error?: string | null;
    request: Record<string, unknown>;
    result?: Record<string, unknown> | null;
    events?: Array<{kind: string; timestamp: string; data: Record<string, unknown>}>;
  }
}
