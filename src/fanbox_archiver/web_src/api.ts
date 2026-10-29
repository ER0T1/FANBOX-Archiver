namespace FanboxUI {
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

  export function getPosts(params: URLSearchParams): Promise<Page<PostSummary>> {
    return requestJson<Page<PostSummary>>(`/api/posts?${params.toString()}`);
  }

  export function getPost(postId: string, params: URLSearchParams): Promise<PostDetail> {
    const query = params.toString();
    return requestJson<PostDetail>(
      `/api/posts/${encodeURIComponent(postId)}${query ? `?${query}` : ""}`,
    );
  }

  export function getCreators(): Promise<{items: CreatorSummary[]}> {
    return requestJson<{items: CreatorSummary[]}>("/api/creators");
  }

  export function getCreator(creatorId: string): Promise<CreatorDetail> {
    return requestJson<CreatorDetail>(`/api/creators/${encodeURIComponent(creatorId)}`);
  }

  export function getCreatorProfile(
    creatorId: string, version: number | null = null,
  ): Promise<CreatorProfile> {
    const query = version === null ? "" : `?version=${version}`;
    return requestJson<CreatorProfile>(
      `/api/creators/${encodeURIComponent(creatorId)}/profile${query}`,
    );
  }

  export function getFanCards(params: URLSearchParams): Promise<{items: FanCardSummary[]}> {
    const query = params.toString();
    return requestJson<{items: FanCardSummary[]}>(`/api/fancards${query ? `?${query}` : ""}`);
  }

  export function getFanCard(
    creatorId: string, month: string, version: number | null = null,
  ): Promise<FanCardDetail> {
    const query = version === null ? "" : `?version=${version}`;
    return requestJson<FanCardDetail>(
      `/api/fancards/${encodeURIComponent(creatorId)}/${encodeURIComponent(month)}${query}`,
    );
  }

  export function getSettings(): Promise<SettingsResponse> {
    return requestJson<SettingsResponse>("/api/config");
  }

  export function saveSettings(patch: SettingsPatch, sessionToken: string): Promise<{saved: boolean}> {
    return requestJson<{saved: boolean}>("/api/config", {
      method: "PATCH",
      headers: {"Content-Type": "application/json", "X-Fanbox-Token": sessionToken},
      body: JSON.stringify(patch),
    });
  }

  export function getJobs(): Promise<{items: WebJob[]}> {
    return requestJson<{items: WebJob[]}>("/api/jobs");
  }

  export function getJob(jobId: string): Promise<WebJob> {
    return requestJson<WebJob>(`/api/jobs/${encodeURIComponent(jobId)}`);
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
