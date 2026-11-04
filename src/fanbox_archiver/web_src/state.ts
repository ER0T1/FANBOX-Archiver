namespace FanboxUI {
  export type View = "posts" | "creators" | "creator" | "backup" | "maintenance" | "settings";
  export type CreatorTab = "profile" | "posts" | "fancards";

  export interface AppState {
    view: View;
    page: number;
    postOrder: SortOrder;
    q: string;
    tag: string;
    current: string | FanCardSelection | null;
    postNavigation: PostNavigation | null;
    creatorId: string | null;
    creatorTab: CreatorTab;
    creator: CreatorDetail | null;
    creatorProfile: CreatorProfile | null;
    jobFilter: string;
    jobPage: number;
    jobOrder: SortOrder;
    verifyPage: number;
    verifyOrder: SortOrder;
    verifyJobId: string | null;
    activeJob: WebJob | null;
    backupScreen: "form" | "history" | "job";
    backupJobId: string | null;
    settingsTab: SettingsTab;
  }

  export function createInitialState(): AppState {
    return {
      view: "posts",
      page: 1,
      postOrder: "desc",
      q: "",
      tag: "",
      current: null,
      postNavigation: null,
      creatorId: null,
      creatorTab: "profile",
      creator: null,
      creatorProfile: null,
      jobFilter: "all",
      jobPage: 1,
      jobOrder: "desc",
      verifyPage: 1,
      verifyOrder: "desc",
      verifyJobId: null,
      activeJob: null,
      backupScreen: "form",
      backupJobId: null,
      settingsTab: "general",
    };
  }
}
