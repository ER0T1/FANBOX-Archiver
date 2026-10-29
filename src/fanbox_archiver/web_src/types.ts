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
    embed?: EmbedPreview | null;
  }

  export interface EmbedPreview {
    kind: string;
    post_id?: string;
    title?: string;
    excerpt?: string | null;
    creator_name?: string | null;
    published_at?: string | null;
    fee_required?: number | null;
    cover_url?: string | null;
    fanbox_url?: string;
    local_available?: boolean;
  }

  export interface PostDetail {
    post_id: string;
    creator_id: string;
    creator_name: string;
    title: string;
    published_at: string | null;
    updated_at: string | null;
    url: string;
    post_type: string;
    fee_required: number | null;
    is_pinned: boolean;
    tags: string[];
    status: string;
    version: number;
    versions: ArchiveVersion[];
    cover_url: string | null;
    blocks: ContentBlock[];
    navigation: PostNavigation;
  }

  export interface CreatorSummary {
    creator_id: string;
    name: string;
    url: string | null;
    post_count: number;
    completed_count: number;
    last_sync: string | null;
    status: string;
    avatar_url: string | null;
    profile_available: boolean;
    profile_version_count: number;
    latest_profile_captured_at: string | null;
  }

  export interface CreatorDetail extends CreatorSummary {
    fancard_count: number;
    fanbox_url: string;
  }

  export interface ProfileItem {
    item_id: string;
    type: string;
    label?: string | null;
    description?: string | null;
    url?: string | null;
    image_url?: string | null;
  }

  export interface CreatorProfile {
    creator_id: string;
    name: string;
    description: string;
    fanbox_url: string;
    has_adult_content: boolean;
    is_accepting_request: boolean;
    is_stopped: boolean;
    profile_items: ProfileItem[];
    cover_url: string | null;
    version: number;
    captured_at: string;
    versions: ArchiveVersion[];
  }

  export interface FanCardSummary {
    creator_id: string;
    creator_name: string;
    target_month: string;
    plan_title: string;
    fee: number | null;
    version_count: number;
    image_url: string | null;
  }

  export interface FanCardDetail extends FanCardSummary {
    description: string;
    perks: unknown[];
    support_start: string | null;
    support_months: string[];
    version: number;
    versions: ArchiveVersion[];
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
    request: {
      creator?: string | null;
      creators?: string[];
      dry_run?: boolean;
      max_posts?: number;
      mode?: string;
      scope?: string;
      include_profile?: boolean | null;
      include_fancard?: boolean | null;
    };
    result?: WebJobResult | null;
    events?: WebJobEvent[];
  }

  export interface WebJobEvent {
    kind: string;
    timestamp: string;
    data: Record<string, unknown>;
  }

  export interface VerificationIssue {
    path: string;
    reason: string;
    post_id?: string | null;
    asset_id?: string | null;
  }

  export interface WebJobResult {
    run_id?: number;
    dry_run?: boolean;
    success?: number;
    failure?: number;
    unchanged?: number;
    selected?: number;
    passed?: boolean;
    issue_count?: number;
    issues?: VerificationIssue[];
    truncated?: boolean;
  }

  export interface BackupJobPayload {
    creators: string[];
    dry_run: boolean;
    max_posts: number;
    mode: "full" | "profile" | "fancard";
    include_profile: boolean;
    include_fancard: boolean;
  }

  export interface DownloadSettings {
    original_images: boolean;
    download_attachments: boolean;
    download_cover: boolean;
    max_concurrent: number;
    retry_count: number;
    request_interval_seconds: number;
    resume: boolean;
    verify_sha256: boolean;
    timeout_seconds: number;
  }

  export interface SyncSettings {
    skip_completed: boolean;
    check_updates: boolean;
    preserve_deleted_posts: boolean;
    max_posts_per_run: number;
    supporting_only: boolean;
    rotate_creators: boolean;
    recent_unchanged_stop_count: number;
  }

  export interface BackupDefaultsSettings {
    dry_run: boolean;
    include_profile: boolean;
    include_fancard: boolean;
  }

  export interface MarkdownSettings {
    enabled: boolean;
    yaml_front_matter: boolean;
    relative_image_paths: boolean;
    preserve_original_order: boolean;
  }

  export interface LoggingSettings {
    level: string;
    write_to_file: boolean;
    keep_days: number;
  }

  export interface EditableSettings {
    download: DownloadSettings;
    sync: SyncSettings;
    backup_defaults: BackupDefaultsSettings;
    markdown: MarkdownSettings;
    logging: LoggingSettings;
  }

  export interface SettingsResponse {
    editable: EditableSettings;
    storage: {output_dir: string; database: string};
    config_path: string | null;
    writable: boolean;
  }

  export interface SettingsPatch {
    download: Omit<DownloadSettings, "max_concurrent">;
    sync: Omit<SyncSettings, "supporting_only">;
    backup_defaults: BackupDefaultsSettings;
    markdown: MarkdownSettings;
    logging: LoggingSettings;
  }
}
