namespace FanboxUI {
  export interface CreatorShellActions {
    onBack(): void;
    onTab(tab: CreatorTab): void;
  }

  export interface FanCardListActions {
    onOpen(creatorId: string, month: string): void;
  }

  export interface FanCardReaderActions {
    onBack(): void;
    versionSelect: HTMLElement;
  }

  export function renderCreatorsPage(
    creators: CreatorSummary[], query: string, onOpen: (creatorId: string) => void,
  ): HTMLElement {
    const term = query.toLocaleLowerCase();
    const items = creators.filter(item =>
      `${item.name} ${item.creator_id}`.toLocaleLowerCase().includes(term));
    const cards = items.map(item => h("button", {
      type: "button", class: "creator-card", onclick: () => onOpen(item.creator_id),
    },
    item.avatar_url
      ? h("img", {src: item.avatar_url, alt: "", loading: "lazy"})
      : h("span", {class: "avatar"}, item.name.slice(0, 1)),
    h("span", {class: "post-main"}, h("strong", {}, item.name),
      h("small", {}, `${item.creator_id} · ${item.post_count} 篇投稿`)),
    h("span", {class: `badge status-${item.status}`}, item.status)));
    return h("section", {class: "page"},
      h("header", {class: "heading"}, h("div", {},
        h("p", {class: "eyebrow"}, "CREATORS"), h("h1", {}, "創作者"),
        h("p", {}, `${items.length} 位符合目前條件`))),
      h("div", {class: "creator-grid"},
        cards.length ? cards : h("p", {class: "empty"}, "沒有符合條件的創作者。")));
  }

  export function renderCreatorShell(
    creator: CreatorDetail, tab: CreatorTab, content: HTMLElement,
    profile: CreatorProfile | null, actions: CreatorShellActions,
  ): HTMLElement {
    const tabs: Array<[CreatorTab, string, string]> = [
      ["profile", "個人資料", "PROFILE"], ["posts", "投稿", "POSTS"],
      ["fancards", "粉絲卡", "FAN CARD"],
    ];
    return h("section", {class: "page creator-page", "data-creator-id": creator.creator_id},
      h("button", {type: "button", class: "back", onclick: actions.onBack}, "← 回到創作者"),
      h("header", {class: `creator-hero${profile?.cover_url ? " has-cover" : ""}`},
        profile?.cover_url ? h("img", {class: "creator-cover", src: profile.cover_url, alt: ""}) : null,
        creator.avatar_url
          ? h("img", {src: creator.avatar_url, alt: ""})
          : h("span", {class: "avatar large"}, creator.name.slice(0, 1)),
        h("div", {}, h("p", {class: "eyebrow"}, `@${creator.creator_id}`), h("h1", {}, creator.name),
          h("p", {}, `${creator.post_count} 篇投稿 · ${creator.fancard_count} 張粉絲卡`)),
        h("a", {class: "external-button", href: creator.fanbox_url, target: "_blank", rel: "noreferrer"}, "開啟 FANBOX ↗")),
      h("nav", {class: "subnav", "aria-label": "創作者頁面"}, tabs.map(([key, zh, en]) => h("button", {
        type: "button", class: key === tab ? "active" : "", "data-creator-tab": key,
        onclick: () => actions.onTab(key),
      }, h("strong", {}, zh), h("small", {}, en)))),
      h("div", {class: "creator-content", "aria-live": "polite"}, content));
  }

  export function renderCreatorProfile(
    creator: CreatorDetail, profile: CreatorProfile | null, versionSelect: HTMLElement | null,
  ): HTMLElement {
    const safeLinks = (profile?.profile_items ?? []).filter(item => item.url?.startsWith("https://"));
    const profileImages = (profile?.profile_items ?? []).filter(item => item.image_url);
    return h("div", {class: "profile-layout"},
      !profile ? h("section", {class: "profile-empty"}, h("p", {class: "eyebrow"}, "PROFILE ARCHIVE"),
        h("h2", {}, "尚未備份個人資料"),
        h("p", {}, "執行新版備份後，這裡會顯示離線可讀的自我介紹、連結與歷史版本。")) : null,
      profile ? h("section", {class: "info-panel profile-about"}, h("p", {class: "eyebrow"}, "ABOUT"),
        h("h2", {}, "關於創作者"),
        profileImages.length ? h("div", {class: "profile-gallery", "aria-label": "創作者 Profile 圖片"},
          profileImages.map((item, index) => h("a", {href: item.image_url, target: "_blank"},
            h("img", {src: item.image_url, alt: item.label || `Profile 圖片 ${index + 1}`, loading: "lazy"})))) : null,
        profile.description ? h("p", {class: "body-text"}, profile.description)
          : h("p", {class: "profile-about-empty"}, "這位創作者尚未提供文字或圖片形式的個人介紹。")) : null,
      safeLinks.length ? h("section", {class: "info-panel profile-links"}, h("p", {class: "eyebrow"}, "LINKS"),
        h("h2", {}, "公開連結"), h("div", {class: "link-grid"}, safeLinks.map(item => h("a", {
          href: item.url, target: "_blank", rel: "noreferrer",
        }, h("strong", {}, item.label || item.type || "外部連結"),
        item.description ? h("span", {}, item.description) : null)))) : null,
      profile ? h("section", {class: "info-panel profile-meta"}, h("p", {class: "eyebrow"}, "ARCHIVE METADATA"),
        h("h2", {}, "狀態與版本"), h("div", {class: "status-list"},
          profile.has_adult_content ? h("span", {class: "profile-flag adult"}, "成人內容") : h("span", {class: "profile-flag"}, "一般內容"),
          h("span", {class: "profile-flag"}, profile.is_accepting_request ? "開放委託" : "未開放委託"),
          profile.is_stopped ? h("span", {class: "profile-flag danger"}, "已停止活動") : h("span", {class: "profile-flag"}, "持續活動")),
        h("dl", {}, h("div", {}, h("dt", {}, "捕捉時間"), h("dd", {}, formatDate(profile.captured_at))),
          h("div", {}, h("dt", {}, "版本"), h("dd", {}, versionSelect)))) : null,
      h("section", {class: "profile-stats"},
        h("div", {}, h("strong", {}, creator.post_count), h("span", {}, "投稿")),
        h("div", {}, h("strong", {}, creator.completed_count), h("span", {}, "完整備份")),
        h("div", {}, h("strong", {}, creator.fancard_count), h("span", {}, "粉絲卡"))));
  }

  export function renderFanCardList(data: {items: FanCardSummary[]}, actions: FanCardListActions): HTMLElement {
    const cards = data.items.map(item => h("button", {
      type: "button", class: "fancard-card", onclick: () => actions.onOpen(item.creator_id, item.target_month),
    },
    item.image_url
      ? h("img", {src: item.image_url, alt: `${item.creator_name} 粉絲卡`, loading: "lazy"})
      : h("div", {class: "card-placeholder"}, "無卡面"),
    h("span", {class: "post-main"}, h("span", {class: "eyebrow"}, item.target_month),
      h("strong", {}, item.plan_title || "方案未命名"),
      h("small", {}, `${feeLabel(item.fee)}/月 · ${item.version_count} 個版本`))));
    return h("div", {class: "fancard-grid"},
      cards.length ? cards : h("p", {class: "empty"}, "尚未備份粉絲卡。"));
  }

  export function renderFanCardReader(card: FanCardDetail, actions: FanCardReaderActions): HTMLElement {
    return h("article", {class: "reader fancard-reader"},
      h("button", {type: "button", class: "back", onclick: actions.onBack}, "← 回到粉絲卡"),
      card.image_url
        ? h("a", {href: card.image_url, target: "_blank"},
          h("img", {class: "card-image", src: card.image_url, alt: `${card.creator_name} 粉絲卡`}))
        : h("div", {class: "card-placeholder large"}, "本月未提供自訂卡面"),
      h("header", {class: "reader-heading"}, h("p", {class: "eyebrow"}, `${card.target_month} · ${card.creator_id}`),
        h("h1", {}, card.creator_name), h("p", {}, `${card.plan_title || "方案未命名"} · ${feeLabel(card.fee)}/月`),
        actions.versionSelect),
      h("section", {class: "content"}, h("h2", {}, "方案資訊"),
        h("p", {class: "body-text"}, card.description || "（無方案說明）"),
        card.support_start ? h("p", {}, `支援開始：${formatDate(card.support_start)}`) : null,
        card.support_months.length ? h("p", {}, `保存月份：${card.support_months.join("、")}`) : null,
        card.perks.length ? h("pre", {}, JSON.stringify(card.perks, null, 2)) : null));
  }
}
