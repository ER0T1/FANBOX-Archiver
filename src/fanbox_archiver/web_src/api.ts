namespace FanboxUI {
  /** True when a request was given up because the user moved on (see `beginLoad` in app.ts). */
  export function isAbortError(error: unknown): boolean {
    return typeof error === "object" && error !== null && (error as {name?: unknown}).name === "AbortError";
  }

  // Page reads take the signal of the load that started them, so leaving the page cancels them.
  // Writes (start backup, save settings, sign in/out…) never take one: they always run to the end.
  export async function requestJson<T>(url: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers);
    if (!headers.has("Accept")) headers.set("Accept", "application/json");
    const response = await fetch(url, {...options, headers});
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body: unknown = await response.json();
        if (body && typeof body === "object" && "detail" in body) {
          detail = String((body as {detail: unknown}).detail);
        }
      } catch {
        // Keep the status-based fallback when the response is not JSON.
      }
      throw new Error(detail);
    }
    return response.json() as Promise<T>;
  }

  export function getPosts(params: URLSearchParams, signal?: AbortSignal): Promise<PostPage> {
    return requestJson<PostPage>(`/api/posts?${params.toString()}`, {signal});
  }

  export function getPost(postId: string, params: URLSearchParams, signal?: AbortSignal): Promise<PostDetail> {
    const query = params.toString();
    return requestJson<PostDetail>(
      `/api/posts/${encodeURIComponent(postId)}${query ? `?${query}` : ""}`, {signal},
    );
  }

  export function getCreators(signal?: AbortSignal): Promise<{items: CreatorSummary[]}> {
    return requestJson<{items: CreatorSummary[]}>("/api/creators", {signal});
  }

  export function getCreator(creatorId: string, signal?: AbortSignal): Promise<CreatorDetail> {
    return requestJson<CreatorDetail>(`/api/creators/${encodeURIComponent(creatorId)}`, {signal});
  }

  export function getCreatorProfile(
    creatorId: string, version: number | null = null, signal?: AbortSignal,
  ): Promise<CreatorProfile> {
    const query = version === null ? "" : `?version=${version}`;
    return requestJson<CreatorProfile>(
      `/api/creators/${encodeURIComponent(creatorId)}/profile${query}`, {signal},
    );
  }

  export function getFanCards(params: URLSearchParams, signal?: AbortSignal): Promise<{items: FanCardSummary[]}> {
    const query = params.toString();
    return requestJson<{items: FanCardSummary[]}>(`/api/fancards${query ? `?${query}` : ""}`, {signal});
  }

  export function getFanCard(
    creatorId: string, month: string, version: number | null = null, signal?: AbortSignal,
  ): Promise<FanCardDetail> {
    const query = version === null ? "" : `?version=${version}`;
    return requestJson<FanCardDetail>(
      `/api/fancards/${encodeURIComponent(creatorId)}/${encodeURIComponent(month)}${query}`, {signal},
    );
  }

  export function getSettings(signal?: AbortSignal): Promise<SettingsResponse> {
    return requestJson<SettingsResponse>("/api/config", {signal});
  }

  export function saveSettings(patch: SettingsSavePatch, sessionToken: string): Promise<SettingsSaveResult> {
    return requestJson<SettingsSaveResult>("/api/config", {
      method: "PATCH",
      headers: {"Content-Type": "application/json", "X-Fanbox-Token": sessionToken},
      body: JSON.stringify(patch),
    });
  }

  export function getScheduleStatus(signal?: AbortSignal): Promise<ScheduleStatus> {
    return requestJson<ScheduleStatus>("/api/schedule", {signal});
  }

  export function previewSchedule(schedule: ScheduleSettingsPatch, sessionToken: string): Promise<SchedulePreview> {
    return requestJson<SchedulePreview>("/api/schedule/preview", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Fanbox-Token": sessionToken},
      body: JSON.stringify(schedule),
    });
  }

  export function runScheduleNow(sessionToken: string): Promise<WebJob> {
    return requestJson<WebJob>("/api/schedule/run", {
      method: "POST",
      headers: {"X-Fanbox-Token": sessionToken},
    });
  }

  export function getAuthStatus(sessionToken: string, signal?: AbortSignal): Promise<AuthStatus> {
    return requestJson<AuthStatus>("/api/auth/status", {
      headers: {"X-Fanbox-Token": sessionToken}, signal,
    });
  }

  export function startAuthLogin(sessionToken: string): Promise<AuthJob> {
    return requestJson<AuthJob>("/api/auth/login", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Fanbox-Token": sessionToken},
      body: JSON.stringify({timeout_seconds: 600}),
    });
  }

  export function cancelAuthLogin(jobId: string, sessionToken: string): Promise<AuthJob> {
    return requestJson<AuthJob>(`/api/auth/login/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST", headers: {"X-Fanbox-Token": sessionToken},
    });
  }

  export function logoutAuth(sessionToken: string): Promise<AuthStatus> {
    return requestJson<AuthStatus>("/api/auth/logout", {
      method: "POST", headers: {"X-Fanbox-Token": sessionToken},
    });
  }

  export function getDiagnostics(sessionToken: string, signal?: AbortSignal): Promise<DiagnosticsInfo> {
    return requestJson<DiagnosticsInfo>("/api/diagnostics", {headers: {"X-Fanbox-Token": sessionToken}, signal});
  }

  export function openDiagnosticsFolder(target: FolderTarget, sessionToken: string): Promise<{opened: FolderTarget}> {
    return requestJson<{opened: FolderTarget}>("/api/diagnostics/open", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Fanbox-Token": sessionToken},
      body: JSON.stringify({target}),
    });
  }

  export function getJobs(
    params: URLSearchParams = new URLSearchParams({page_size: "1"}), signal?: AbortSignal,
  ): Promise<JobPage> {
    return requestJson<JobPage>(`/api/jobs?${params}`, {signal});
  }

  export function getJob(jobId: string, signal?: AbortSignal): Promise<WebJob> {
    return requestJson<WebJob>(`/api/jobs/${encodeURIComponent(jobId)}`, {signal});
  }

  export function startBackupJob(payload: BackupJobPayload, sessionToken: string): Promise<WebJob> {
    return requestJson<WebJob>("/api/jobs/backup", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Fanbox-Token": sessionToken},
      body: JSON.stringify(payload),
    });
  }

  export function startVerificationJob(sessionToken: string): Promise<WebJob> {
    return requestJson<WebJob>("/api/jobs/verify", {
      method: "POST", headers: {"X-Fanbox-Token": sessionToken},
    });
  }

  export function cancelJob(jobId: string, sessionToken: string): Promise<WebJob> {
    return requestJson<WebJob>(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST", headers: {"X-Fanbox-Token": sessionToken},
    });
  }

  export function retryJob(jobId: string, sessionToken: string): Promise<WebJob> {
    return requestJson<WebJob>(`/api/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST", headers: {"X-Fanbox-Token": sessionToken},
    });
  }
}
