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

  export function perkStatusClass(status: string): string {
    const safeStatus = ["accessible", "inaccessible", "unavailable", "available", "unknown"].includes(status)
      ? status : "unknown";
    return `perk-status status-${safeStatus}`;
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
      h("small", {}, t("creators.card_meta", {creator_id: item.creator_id, count: item.post_count}))),
    h("span", {class: `badge status-${item.status}`}, item.status)));
    return h("section", {class: "page"},
      h("header", {class: "heading"}, h("div", {},
        h("p", {class: "eyebrow"}, t("creators.eyebrow")), h("h1", {}, t("creators.title")),
        h("p", {}, t("creators.matching", {count: items.length})))),
      h("div", {class: "creator-grid"},
        cards.length ? cards : h("p", {class: "empty"}, t("creators.empty"))));
  }

  export function renderCreatorShell(
    creator: CreatorDetail, tab: CreatorTab, content: HTMLElement,
    profile: CreatorProfile | null, actions: CreatorShellActions,
  ): HTMLElement {
    const tabs: Array<[CreatorTab, string, string]> = [
      ["profile", t("creator.tab_profile"), "PROFILE"], ["posts", t("creator.tab_posts"), "POSTS"],
      ["fancards", t("creator.tab_fancards"), "FAN CARD"],
    ];
    return h("section", {class: "page creator-page", "data-creator-id": creator.creator_id},
      h("button", {type: "button", class: "back", onclick: actions.onBack}, t("creator.back")),
      h("header", {class: `creator-hero${profile?.cover_url ? " has-cover" : ""}`},
        profile?.cover_url ? h("img", {class: "creator-cover", src: profile.cover_url, alt: ""}) : null,
        creator.avatar_url
          ? h("img", {src: creator.avatar_url, alt: ""})
          : h("span", {class: "avatar large"}, creator.name.slice(0, 1)),
        h("div", {}, h("p", {class: "eyebrow"}, `@${creator.creator_id}`), h("h1", {}, creator.name),
          h("p", {}, t("creator.hero_meta", {posts: creator.post_count, cards: creator.fancard_count}))),
        h("a", {class: "external-button", href: creator.fanbox_url, target: "_blank", rel: "noreferrer"}, t("creator.open_fanbox"))),
      h("nav", {class: "subnav", "aria-label": t("creator.nav_label")}, tabs.map(([key, zh, en]) => h("button", {
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
        h("h2", {}, t("profile.empty_title")),
        h("p", {}, t("profile.empty_body"))) : null,
      profile ? h("section", {class: "info-panel profile-about"}, h("p", {class: "eyebrow"}, "ABOUT"),
        h("h2", {}, t("profile.about_title")),
        profileImages.length ? h("div", {class: "profile-gallery", "aria-label": t("profile.gallery_label")},
          profileImages.map((item, index) => h("a", {href: item.image_url, target: "_blank"},
            h("img", {src: item.image_url, alt: item.label || t("profile.image_alt", {number: index + 1}), loading: "lazy"})))) : null,
        profile.description ? h("p", {class: "body-text"}, profile.description)
          : h("p", {class: "profile-about-empty"}, t("profile.about_empty"))) : null,
      safeLinks.length ? h("section", {class: "info-panel profile-links"}, h("p", {class: "eyebrow"}, "LINKS"),
        h("h2", {}, t("profile.links_title")), h("div", {class: "link-grid"}, safeLinks.map(item => h("a", {
          href: item.url, target: "_blank", rel: "noreferrer",
        }, h("strong", {}, item.label || item.type || t("profile.link_fallback")),
        item.description ? h("span", {}, item.description) : null)))) : null,
      profile ? h("section", {class: "info-panel profile-meta"}, h("p", {class: "eyebrow"}, "ARCHIVE METADATA"),
        h("h2", {}, t("profile.meta_title")), h("div", {class: "status-list"},
          profile.has_adult_content ? h("span", {class: "profile-flag adult"}, t("profile.adult")) : h("span", {class: "profile-flag"}, t("profile.general")),
          h("span", {class: "profile-flag"}, profile.is_accepting_request ? t("profile.accepting") : t("profile.not_accepting")),
          profile.is_stopped ? h("span", {class: "profile-flag danger"}, t("profile.stopped")) : h("span", {class: "profile-flag"}, t("profile.active"))),
        h("dl", {}, h("div", {}, h("dt", {}, t("profile.captured_at")), h("dd", {}, formatDate(profile.captured_at))),
          h("div", {}, h("dt", {}, t("common.version")), h("dd", {}, versionSelect)))) : null,
      h("section", {class: "profile-stats"},
        h("div", {}, h("strong", {}, creator.post_count), h("span", {}, t("profile.stat_posts"))),
        h("div", {}, h("strong", {}, creator.completed_count), h("span", {}, t("profile.stat_completed"))),
        h("div", {}, h("strong", {}, creator.fancard_count), h("span", {}, t("profile.stat_fancards")))));
  }

  export function renderFanCardList(data: {items: FanCardSummary[]}, actions: FanCardListActions): HTMLElement {
    const cards = data.items.map(item => h("button", {
      type: "button", class: "fancard-card", onclick: () => actions.onOpen(item.creator_id, item.target_month),
    },
    item.image_url
      ? h("img", {src: item.image_url, alt: t("fancards.image_alt", {creator: item.creator_name}), loading: "lazy"})
      : h("div", {class: "card-placeholder"}, t("fancards.no_image")),
    h("span", {class: "post-main"}, h("span", {class: "eyebrow"}, item.target_month),
      h("strong", {}, item.plan_title || t("fancards.plan_untitled")),
      h("small", {}, t("fancards.card_meta", {fee: feeLabel(item.fee), count: item.version_count})))));
    return h("div", {class: "fancard-grid"},
      cards.length ? cards : h("p", {class: "empty"}, t("fancards.empty")));
  }

  export function renderFanCardReader(card: FanCardDetail, actions: FanCardReaderActions): HTMLElement {
    const perks = card.perks.length ? h("section", {class: "perk-section"},
      h("p", {class: "eyebrow"}, "PLAN BENEFITS"), h("h2", {}, t("fancard.perks_title")),
      h("div", {class: "perk-grid"}, card.perks.map(perk => h("article", {class: "perk-card"},
        h("div", {class: "perk-card-heading"}, h("h3", {}, perk.label),
          h("span", {class: perkStatusClass(perk.status)}, perk.status_label)),
        h("p", {}, perk.description),
        perk.guidance ? h("p", {class: "perk-guidance"}, perk.guidance, " ",
          perk.settings_url ? h("a", {href: perk.settings_url, target: "_blank", rel: "noreferrer"},
            `${perk.settings_label || t("fancard.account_settings")} ↗`) : null) : null,
        perk.action_url && perk.action_label ? h("a", {
          class: "perk-action", href: perk.action_url, target: "_blank", rel: "noreferrer",
        }, `${perk.action_label} ↗`) : null)))) : null;
    return h("article", {class: "reader fancard-reader"},
      h("button", {type: "button", class: "back", onclick: actions.onBack}, t("fancard.back")),
      card.image_url
        ? h("a", {href: card.image_url, target: "_blank"},
          h("img", {class: "card-image", src: card.image_url, alt: t("fancards.image_alt", {creator: card.creator_name})}))
        : h("div", {class: "card-placeholder large"}, t("fancard.no_custom_image")),
      h("header", {class: "reader-heading"}, h("p", {class: "eyebrow"}, `${card.target_month} · ${card.creator_id}`),
        h("h1", {}, card.creator_name), h("p", {}, t("fancard.plan_line", {plan: card.plan_title || t("fancards.plan_untitled"), fee: feeLabel(card.fee)})),
        actions.versionSelect),
      h("section", {class: "content"}, h("h2", {}, t("fancard.plan_info")),
        h("p", {class: "body-text"}, card.description || t("fancard.no_description")),
        card.support_start ? h("p", {}, t("fancard.support_start", {time: formatDate(card.support_start)})) : null,
        card.support_months.length ? h("p", {}, t("fancard.saved_months", {months: card.support_months.join(t("fancard.month_separator"))})) : null,
        perks));
  }
}
