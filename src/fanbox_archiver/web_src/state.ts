namespace FanboxUI {
  export type View = "posts" | "creators" | "creator" | "backup" | "maintenance" | "settings";
  export type CreatorTab = "profile" | "posts" | "fancards";

  export interface AppState {
    view: View;
    page: number;
    q: string;
    tag: string;
    current: string | FanCardSelection | null;
    postNavigation: PostNavigation | null;
    creatorId: string | null;
    creatorTab: CreatorTab;
    creator: CreatorDetail | null;
    creatorProfile: CreatorProfile | null;
    jobFilter: string;
    activeJob: WebJob | null;
    backupScreen: "form" | "history" | "job";
    backupJobId: string | null;
  }

  export function createInitialState(): AppState {
    return {
      view: "posts",
      page: 1,
      q: "",
      tag: "",
      current: null,
      postNavigation: null,
      creatorId: null,
      creatorTab: "profile",
      creator: null,
      creatorProfile: null,
      jobFilter: "all",
      activeJob: null,
      backupScreen: "form",
      backupJobId: null,
    };
  }
}
