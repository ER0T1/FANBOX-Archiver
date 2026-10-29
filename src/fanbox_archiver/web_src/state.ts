namespace FanboxUI {
  export type View = "posts" | "creators" | "creator" | "backup" | "maintenance" | "settings";
  export type CreatorTab = "profile" | "posts" | "fancards";

  export interface AppState {
    view: View;
    page: number;
    q: string;
    current: string | FanCardSelection | null;
    postNavigation: PostNavigation | null;
    creatorId: string | null;
    creatorTab: CreatorTab;
    creator: CreatorDetail | null;
    creatorProfile: CreatorProfile | null;
    jobFilter: string;
  }

  export function createInitialState(): AppState {
    return {
      view: "posts",
      page: 1,
      q: "",
      current: null,
      postNavigation: null,
      creatorId: null,
      creatorTab: "profile",
      creator: null,
      creatorProfile: null,
      jobFilter: "all",
    };
  }
}
