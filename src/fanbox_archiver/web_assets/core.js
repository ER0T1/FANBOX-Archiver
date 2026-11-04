"use strict";
var FanboxUI;
(function (FanboxUI) {
    const placeholder = /\{([a-z_][a-z0-9_]*)\}/g;
    let catalog = { locale: "zh-Hant", intl: "zh-Hant", base: "zh-Hant", messages: {} };
    let numberFormat = new Intl.NumberFormat("zh-Hant");
    let pluralRules = new Intl.PluralRules("zh-Hant");
    const reported = new Set();
    function setI18nCatalog(value) {
        if (!value || typeof value !== "object")
            return;
        const data = value;
        if (!data.messages || typeof data.messages !== "object")
            return;
        catalog = {
            locale: String(data.locale || "zh-Hant"), intl: String(data.intl || "zh-Hant"),
            base: String(data.base || "zh-Hant"), messages: data.messages,
        };
        try {
            numberFormat = new Intl.NumberFormat(catalog.intl);
            pluralRules = new Intl.PluralRules(catalog.intl);
        }
        catch {
            numberFormat = new Intl.NumberFormat("zh-Hant");
            pluralRules = new Intl.PluralRules("zh-Hant");
        }
    }
    FanboxUI.setI18nCatalog = setI18nCatalog;
    function currentLocale() {
        return catalog.locale;
    }
    FanboxUI.currentLocale = currentLocale;
    function formatNumber(value) {
        return numberFormat.format(value);
    }
    FanboxUI.formatNumber = formatNumber;
    function t(key, params = {}) {
        let message = catalog.messages[key];
        if (message === undefined) {
            if (!reported.has(key)) {
                reported.add(key);
                globalThis.console?.warn?.(`[i18n] missing key: ${key}`);
            }
            return key;
        }
        if (typeof message !== "string") {
            const count = Number(params.count ?? 0);
            message = message[pluralRules.select(count)] ?? message.other ?? key;
        }
        return message.replace(placeholder, (match, name) => {
            const value = params[name];
            if (value === undefined)
                return match;
            return typeof value === "number" ? formatNumber(value) : value;
        });
    }
    FanboxUI.t = t;
    function applyI18n(root) {
        if (!Object.keys(catalog.messages).length)
            return;
        for (const element of root.querySelectorAll("[data-i18n]")) {
            const key = element.dataset.i18n;
            if (key)
                element.textContent = t(key);
        }
        for (const element of root.querySelectorAll("[data-i18n-attr]")) {
            for (const pair of (element.dataset.i18nAttr ?? "").split(";")) {
                const [attribute, key] = pair.split(":").map(part => part.trim());
                if (attribute && key)
                    element.setAttribute(attribute, t(key));
            }
        }
    }
    FanboxUI.applyI18n = applyI18n;
    setI18nCatalog(globalThis.FanboxI18n);
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function createInitialState() {
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
    FanboxUI.createInitialState = createInitialState;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    const FALLBACK_TIME_ZONE = "Asia/Taipei";
    const buildFormatter = (zone) => new Intl.DateTimeFormat("en-CA", {
        timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    });
    let displayTimeZone = FALLBACK_TIME_ZONE;
    let dateTimeFormatter = buildFormatter(displayTimeZone);
    const explicitOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i;
    function setDisplayTimeZone(zone) {
        if (!zone || zone === displayTimeZone)
            return;
        try {
            dateTimeFormatter = buildFormatter(zone);
            displayTimeZone = zone;
        }
        catch {
        }
    }
    FanboxUI.setDisplayTimeZone = setDisplayTimeZone;
    function getDisplayTimeZone() {
        return displayTimeZone;
    }
    FanboxUI.getDisplayTimeZone = getDisplayTimeZone;
    function formatDate(value) {
        if (!value)
            return "—";
        const text = String(value).trim();
        if (!explicitOffset.test(text))
            return FanboxUI.t("common.timezone_unknown", { value: text });
        const date = new Date(text);
        if (Number.isNaN(date.valueOf()))
            return text;
        const parts = Object.fromEntries(dateTimeFormatter.formatToParts(date).map(part => [part.type, part.value]));
        return FanboxUI.t("common.datetime", { year: parts.year ?? "", month: parts.month ?? "", day: parts.day ?? "",
            hour: parts.hour ?? "", minute: parts.minute ?? "" });
    }
    FanboxUI.formatDate = formatDate;
    function humanBytes(value) {
        const bytes = Number(value ?? 0);
        if (!Number.isFinite(bytes) || bytes <= 0)
            return "0 B";
        const units = ["B", "KB", "MB", "GB", "TB"];
        const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
        const scaled = bytes / (1024 ** index);
        const digits = index === 0 || scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
        return `${scaled.toFixed(digits)} ${units[index]}`;
    }
    FanboxUI.humanBytes = humanBytes;
    function feeLabel(value) {
        if (value === null || value === undefined)
            return FanboxUI.t("common.fee_unknown");
        return Number(value) <= 0 ? FanboxUI.t("common.fee_public") : FanboxUI.t("common.fee_amount", { amount: Number(value) });
    }
    FanboxUI.feeLabel = feeLabel;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function appendChild(parent, child) {
        if (Array.isArray(child)) {
            for (const item of child)
                appendChild(parent, item);
        }
        else if (child instanceof Node) {
            parent.append(child);
        }
        else if (child !== null && child !== undefined && child !== false) {
            parent.append(document.createTextNode(String(child)));
        }
    }
    function h(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs)) {
            if (key.startsWith("on") && typeof value === "function") {
                node.addEventListener(key.slice(2), value);
            }
            else if (value !== null && value !== undefined && value !== false) {
                node.setAttribute(key, value === true ? "" : String(value));
            }
        }
        for (const child of children)
            appendChild(node, child);
        return node;
    }
    FanboxUI.h = h;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function customSelect(options) {
        const normalized = options.options.map(option => ({ value: String(option.value), label: String(option.label) }));
        let selectedValue = String(options.value ?? normalized[0]?.value ?? "");
        const menuId = `${options.id || "select"}-menu-${Math.random().toString(36).slice(2, 9)}`;
        const summaryText = FanboxUI.h("span", { class: "select-value" });
        const menu = FanboxUI.h("div", { id: menuId, class: "select-menu", role: "listbox", "aria-label": options.label });
        const root = FanboxUI.h("details", { class: "custom-select", id: options.id });
        const summary = FanboxUI.h("summary", { role: "combobox", "aria-label": options.label, "aria-controls": menuId,
            "aria-expanded": "false", "aria-haspopup": "listbox" }, summaryText);
        let disabledFlag = false;
        const isDisabled = () => disabledFlag || Boolean(root.closest("fieldset")?.disabled);
        const setDisabled = (value) => {
            disabledFlag = value;
            if (value) {
                root.setAttribute("aria-disabled", "true");
                root.open = false;
            }
            else {
                root.removeAttribute("aria-disabled");
            }
            summary.tabIndex = value ? -1 : 0;
            summary.setAttribute("aria-disabled", value ? "true" : "false");
        };
        const update = (nextValue) => {
            selectedValue = String(nextValue);
            const selected = normalized.find(option => option.value === selectedValue) ?? normalized[0];
            summaryText.textContent = selected?.label ?? "";
            for (const item of menu.querySelectorAll('[role="option"]')) {
                const active = item.dataset.value === selectedValue;
                item.setAttribute("aria-selected", active ? "true" : "false");
                item.tabIndex = active ? 0 : -1;
            }
        };
        for (const option of normalized) {
            menu.append(FanboxUI.h("button", { type: "button", role: "option", "data-value": option.value, onclick: () => {
                    const changed = selectedValue !== option.value;
                    update(option.value);
                    root.open = false;
                    summary.focus();
                    if (changed) {
                        options.onChange?.(option.value);
                        root.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                } }, option.label));
        }
        summary.addEventListener("click", event => {
            if (isDisabled())
                event.preventDefault();
        });
        summary.addEventListener("keydown", event => {
            if (isDisabled()) {
                if (["ArrowDown", "ArrowUp", "Home", "End", "Enter", " "].includes(event.key))
                    event.preventDefault();
                return;
            }
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key))
                return;
            event.preventDefault();
            root.open = true;
            const choices = [...menu.querySelectorAll('[role="option"]')];
            const selectedIndex = Math.max(0, choices.findIndex(item => item.dataset.value === selectedValue));
            const targetIndex = event.key === "End" ? choices.length - 1 : event.key === "ArrowUp"
                ? Math.max(0, selectedIndex - 1) : event.key === "ArrowDown"
                ? Math.min(choices.length - 1, selectedIndex + 1) : 0;
            choices[targetIndex]?.focus();
        });
        menu.addEventListener("keydown", event => {
            const choices = [...menu.querySelectorAll('[role="option"]')];
            const index = choices.indexOf(document.activeElement);
            if (event.key === "Escape") {
                event.preventDefault();
                root.open = false;
                summary.focus();
                return;
            }
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key))
                return;
            event.preventDefault();
            const targetIndex = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1
                : event.key === "ArrowDown" ? Math.min(choices.length - 1, index + 1) : Math.max(0, index - 1);
            choices[targetIndex]?.focus();
        });
        root.addEventListener("toggle", () => {
            if (root.open && isDisabled()) {
                root.open = false;
                return;
            }
            summary.setAttribute("aria-expanded", root.open ? "true" : "false");
            if (root.open)
                menu.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
        });
        Object.defineProperty(root, "value", { get: () => selectedValue, set: update });
        Object.defineProperty(root, "disabled", { get: () => disabledFlag, set: setDisabled });
        root.append(summary, menu);
        update(selectedValue);
        setDisabled(Boolean(options.disabled));
        return root;
    }
    FanboxUI.customSelect = customSelect;
    function sortToggle(order, onChange, label = FanboxUI.t("common.sort_time")) {
        const text = order === "desc" ? FanboxUI.t("common.sort_desc_button") : FanboxUI.t("common.sort_asc_button");
        return FanboxUI.h("button", { type: "button", class: "sort-toggle", "data-order": order,
            "aria-label": FanboxUI.t("common.sort_label", { label, order: order === "desc" ? FanboxUI.t("common.sort_desc") : FanboxUI.t("common.sort_asc") }),
            onclick: () => onChange(order === "desc" ? "asc" : "desc") }, text);
    }
    FanboxUI.sortToggle = sortToggle;
    function closeDropdownsOutside(target) {
        for (const dropdown of document.querySelectorAll(".custom-select[open], .page-jump[open]")) {
            if (!(target instanceof Node) || !dropdown.contains(target))
                dropdown.open = false;
        }
    }
    FanboxUI.closeDropdownsOutside = closeDropdownsOutside;
    function closeDropdownsAndFocus() {
        const dropdowns = [...document.querySelectorAll(".custom-select[open], .page-jump[open]")];
        for (const dropdown of dropdowns) {
            dropdown.open = false;
            dropdown.querySelector("summary")?.focus();
        }
        return dropdowns.length > 0;
    }
    FanboxUI.closeDropdownsAndFocus = closeDropdownsAndFocus;
    function renderError(error, onRetry) {
        const message = error instanceof Error ? error.message : String(error);
        return FanboxUI.h("section", { class: "panel error" }, FanboxUI.h("p", { class: "eyebrow" }, "ERROR"), FanboxUI.h("h1", {}, FanboxUI.t("common.error_title")), FanboxUI.h("p", {}, message), FanboxUI.h("button", { type: "button", onclick: onRetry }, FanboxUI.t("common.retry")));
    }
    FanboxUI.renderError = renderError;
    function setActiveNavigation(nav, view) {
        const active = view === "creator" ? "creators" : view;
        for (const button of nav.querySelectorAll("button")) {
            button.classList.toggle("active", button.dataset.view === active);
        }
    }
    FanboxUI.setActiveNavigation = setActiveNavigation;
    function setSearchState(search, view, creatorTab) {
        search.disabled = ["backup", "maintenance", "settings"].includes(view)
            || (view === "creator" && creatorTab === "profile");
        search.placeholder = FanboxUI.t(view === "posts" ? "search.posts"
            : view === "creators" ? "search.creators"
                : view === "creator" && creatorTab === "fancards" ? "search.creator_fancards"
                    : view === "creator" && creatorTab === "posts" ? "search.creator_posts"
                        : view === "backup" ? "search.backup"
                            : view === "maintenance" ? "search.maintenance"
                                : view === "settings" ? "search.settings" : "search.creator_profile");
    }
    FanboxUI.setSearchState = setSearchState;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function confirmDialog(options) {
        const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        const titleId = `dialog-title-${Math.random().toString(36).slice(2, 9)}`;
        const cancel = FanboxUI.h("button", { type: "button", class: "dialog-cancel", value: "cancel" }, options.cancelLabel);
        const confirm = FanboxUI.h("button", { type: "button", class: options.danger ? "dialog-confirm danger" : "dialog-confirm primary",
            value: "confirm" }, options.confirmLabel);
        const dialog = FanboxUI.h("dialog", { class: "app-dialog", "aria-labelledby": titleId }, FanboxUI.h("h2", { id: titleId }, options.title), FanboxUI.h("p", {}, options.message), FanboxUI.h("div", { class: "dialog-actions" }, cancel, confirm));
        document.body.append(dialog);
        return new Promise(resolve => {
            let settled = false;
            const finish = (result) => {
                if (settled)
                    return;
                settled = true;
                if (dialog.open)
                    dialog.close();
                dialog.remove();
                returnFocus?.focus();
                resolve(result);
            };
            cancel.addEventListener("click", () => finish(false));
            confirm.addEventListener("click", () => finish(true));
            dialog.addEventListener("cancel", event => { event.preventDefault(); finish(false); });
            dialog.addEventListener("close", () => finish(false));
            if (typeof dialog.showModal === "function")
                dialog.showModal();
            else
                dialog.setAttribute("open", "");
            cancel.focus();
        });
    }
    FanboxUI.confirmDialog = confirmDialog;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function trackChanges(root, fields, onChange) {
        const serialize = (field) => JSON.stringify(field.read());
        const saved = fields.map(serialize);
        let dirty = false;
        const refresh = () => {
            let any = false;
            fields.forEach((field, index) => {
                const changed = serialize(field) !== saved[index];
                any || (any = changed);
                field.node.classList.toggle("is-dirty", changed);
                let badge = field.node.querySelector(":scope > .dirty-badge");
                if (changed && !badge) {
                    badge = FanboxUI.h("span", { class: "dirty-badge" }, FanboxUI.t("common.changed"));
                    field.node.append(badge);
                }
                else if (!changed && badge) {
                    badge.remove();
                }
            });
            if (any !== dirty) {
                dirty = any;
                onChange(dirty);
            }
        };
        let pending;
        const schedule = () => {
            if (pending !== undefined)
                clearTimeout(pending);
            pending = window.setTimeout(() => { pending = undefined; refresh(); }, 0);
        };
        for (const type of ["input", "change", "click"])
            root.addEventListener(type, schedule);
        return { isDirty: () => { refresh(); return dirty; }, refresh };
    }
    FanboxUI.trackChanges = trackChanges;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function isAbortError(error) {
        return typeof error === "object" && error !== null && error.name === "AbortError";
    }
    FanboxUI.isAbortError = isAbortError;
    async function requestJson(url, options = {}) {
        const headers = new Headers(options.headers);
        if (!headers.has("Accept"))
            headers.set("Accept", "application/json");
        const response = await fetch(url, { ...options, headers });
        if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            try {
                const body = await response.json();
                if (body && typeof body === "object" && "detail" in body) {
                    detail = String(body.detail);
                }
            }
            catch {
            }
            throw new Error(detail);
        }
        return response.json();
    }
    FanboxUI.requestJson = requestJson;
    function getPosts(params, signal) {
        return requestJson(`/api/posts?${params.toString()}`, { signal });
    }
    FanboxUI.getPosts = getPosts;
    function getPost(postId, params, signal) {
        const query = params.toString();
        return requestJson(`/api/posts/${encodeURIComponent(postId)}${query ? `?${query}` : ""}`, { signal });
    }
    FanboxUI.getPost = getPost;
    function getCreators(signal) {
        return requestJson("/api/creators", { signal });
    }
    FanboxUI.getCreators = getCreators;
    function getCreator(creatorId, signal) {
        return requestJson(`/api/creators/${encodeURIComponent(creatorId)}`, { signal });
    }
    FanboxUI.getCreator = getCreator;
    function getCreatorProfile(creatorId, version = null, signal) {
        const query = version === null ? "" : `?version=${version}`;
        return requestJson(`/api/creators/${encodeURIComponent(creatorId)}/profile${query}`, { signal });
    }
    FanboxUI.getCreatorProfile = getCreatorProfile;
    function getFanCards(params, signal) {
        const query = params.toString();
        return requestJson(`/api/fancards${query ? `?${query}` : ""}`, { signal });
    }
    FanboxUI.getFanCards = getFanCards;
    function getFanCard(creatorId, month, version = null, signal) {
        const query = version === null ? "" : `?version=${version}`;
        return requestJson(`/api/fancards/${encodeURIComponent(creatorId)}/${encodeURIComponent(month)}${query}`, { signal });
    }
    FanboxUI.getFanCard = getFanCard;
    function getSettings(signal) {
        return requestJson("/api/config", { signal });
    }
    FanboxUI.getSettings = getSettings;
    function saveSettings(patch, sessionToken) {
        return requestJson("/api/config", {
            method: "PATCH",
            headers: { "Content-Type": "application/json", "X-Fanbox-Token": sessionToken },
            body: JSON.stringify(patch),
        });
    }
    FanboxUI.saveSettings = saveSettings;
    function getScheduleStatus(signal) {
        return requestJson("/api/schedule", { signal });
    }
    FanboxUI.getScheduleStatus = getScheduleStatus;
    function previewSchedule(schedule, sessionToken) {
        return requestJson("/api/schedule/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Fanbox-Token": sessionToken },
            body: JSON.stringify(schedule),
        });
    }
    FanboxUI.previewSchedule = previewSchedule;
    function runScheduleNow(sessionToken) {
        return requestJson("/api/schedule/run", {
            method: "POST",
            headers: { "X-Fanbox-Token": sessionToken },
        });
    }
    FanboxUI.runScheduleNow = runScheduleNow;
    function getAuthStatus(sessionToken, signal) {
        return requestJson("/api/auth/status", {
            headers: { "X-Fanbox-Token": sessionToken }, signal,
        });
    }
    FanboxUI.getAuthStatus = getAuthStatus;
    function startAuthLogin(sessionToken) {
        return requestJson("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Fanbox-Token": sessionToken },
            body: JSON.stringify({ timeout_seconds: 600 }),
        });
    }
    FanboxUI.startAuthLogin = startAuthLogin;
    function cancelAuthLogin(jobId, sessionToken) {
        return requestJson(`/api/auth/login/${encodeURIComponent(jobId)}/cancel`, {
            method: "POST", headers: { "X-Fanbox-Token": sessionToken },
        });
    }
    FanboxUI.cancelAuthLogin = cancelAuthLogin;
    function logoutAuth(sessionToken) {
        return requestJson("/api/auth/logout", {
            method: "POST", headers: { "X-Fanbox-Token": sessionToken },
        });
    }
    FanboxUI.logoutAuth = logoutAuth;
    function getDiagnostics(sessionToken, signal) {
        return requestJson("/api/diagnostics", { headers: { "X-Fanbox-Token": sessionToken }, signal });
    }
    FanboxUI.getDiagnostics = getDiagnostics;
    function openDiagnosticsFolder(target, sessionToken) {
        return requestJson("/api/diagnostics/open", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Fanbox-Token": sessionToken },
            body: JSON.stringify({ target }),
        });
    }
    FanboxUI.openDiagnosticsFolder = openDiagnosticsFolder;
    function getJobs(params = new URLSearchParams({ page_size: "1" }), signal) {
        return requestJson(`/api/jobs?${params}`, { signal });
    }
    FanboxUI.getJobs = getJobs;
    function getJob(jobId, signal) {
        return requestJson(`/api/jobs/${encodeURIComponent(jobId)}`, { signal });
    }
    FanboxUI.getJob = getJob;
    function startBackupJob(payload, sessionToken) {
        return requestJson("/api/jobs/backup", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Fanbox-Token": sessionToken },
            body: JSON.stringify(payload),
        });
    }
    FanboxUI.startBackupJob = startBackupJob;
    function startVerificationJob(sessionToken) {
        return requestJson("/api/jobs/verify", {
            method: "POST", headers: { "X-Fanbox-Token": sessionToken },
        });
    }
    FanboxUI.startVerificationJob = startVerificationJob;
    function cancelJob(jobId, sessionToken) {
        return requestJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
            method: "POST", headers: { "X-Fanbox-Token": sessionToken },
        });
    }
    FanboxUI.cancelJob = cancelJob;
    function retryJob(jobId, sessionToken) {
        return requestJson(`/api/jobs/${encodeURIComponent(jobId)}/retry`, {
            method: "POST", headers: { "X-Fanbox-Token": sessionToken },
        });
    }
    FanboxUI.retryJob = retryJob;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function renderPostCard(item, onOpen) {
        return FanboxUI.h("button", {
            type: "button", class: `post-card${item.is_pinned ? " pinned" : ""}`,
            onclick: () => onOpen(item.post_id),
        }, item.cover_url
            ? FanboxUI.h("img", { class: "post-cover", src: item.cover_url, alt: "", loading: "lazy" })
            : FanboxUI.h("span", { class: "post-cover placeholder", "aria-hidden": "true" }, FanboxUI.t("posts.cover_placeholder")), FanboxUI.h("span", { class: "post-main" }, FanboxUI.h("span", { class: "post-meta" }, FanboxUI.formatDate(item.published_at), item.is_pinned ? FanboxUI.h("span", { class: "pin-badge" }, FanboxUI.t("posts.pinned")) : null, FanboxUI.h("span", { class: "fee-badge" }, FanboxUI.feeLabel(item.fee_required))), FanboxUI.h("strong", {}, item.title), FanboxUI.h("small", {}, FanboxUI.t("posts.card_meta", { creator: item.creator_name, post_id: item.post_id, count: item.version_count })), item.tags.length ? FanboxUI.h("span", { class: "post-tags", "aria-label": FanboxUI.t("posts.tags_label", { tags: item.tags.join(FanboxUI.t("posts.tag_separator")) }) }, item.tags.map(tag => FanboxUI.h("span", { class: "post-tag" }, tag))) : null), FanboxUI.h("span", { class: `badge status-${item.status}` }, item.status));
    }
    FanboxUI.renderPostCard = renderPostCard;
    function renderPagination(data, onPage, label = FanboxUI.t("posts.pagination")) {
        if (data.pages <= 1)
            return null;
        const previous = FanboxUI.h("button", {
            type: "button", disabled: data.page <= 1,
            onclick: () => onPage(data.page - 1),
        }, FanboxUI.t("common.previous_page"));
        const next = FanboxUI.h("button", {
            type: "button", disabled: data.page >= data.pages,
            onclick: () => onPage(data.page + 1),
        }, FanboxUI.t("common.next_page"));
        const pageJump = FanboxUI.h("details", { class: "page-jump" }, FanboxUI.h("summary", { "aria-label": FanboxUI.t("common.page_position", { page: data.page, pages: data.pages }) }, `${data.page} / ${data.pages}`), FanboxUI.h("div", { class: "page-menu", role: "listbox", "aria-label": FanboxUI.t("common.page_jump") }, Array.from({ length: data.pages }, (_, index) => {
            const page = index + 1;
            return FanboxUI.h("button", {
                type: "button", role: "option", "aria-selected": page === data.page,
                onclick: () => {
                    pageJump.open = false;
                    onPage(page);
                },
            }, String(page));
        })));
        return FanboxUI.h("nav", { class: "pagination", "aria-label": label }, previous, pageJump, next);
    }
    FanboxUI.renderPagination = renderPagination;
    function renderPostListPage(data, actions) {
        const cards = data.items.map(item => renderPostCard(item, actions.onOpen));
        return FanboxUI.h("section", { class: "page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, FanboxUI.t("posts.eyebrow")), FanboxUI.h("h1", {}, FanboxUI.t("posts.title")), FanboxUI.h("p", {}, FanboxUI.t("posts.total", { count: data.total }))), actions.onOrder ? FanboxUI.sortToggle(actions.order ?? "desc", actions.onOrder, FanboxUI.t("posts.sort_label")) : null), FanboxUI.h("div", { class: "post-list" }, cards.length ? cards : FanboxUI.h("p", { class: "empty" }, FanboxUI.t("posts.empty"))), renderPagination(data, actions.onPage));
    }
    FanboxUI.renderPostListPage = renderPostListPage;
    function renderCreatorPostList(data, actions) {
        const cards = data.items.map(item => renderPostCard(item, actions.onOpen));
        const filter = actions.onTag ? FanboxUI.h("section", { class: "tag-filter", "aria-label": FanboxUI.t("posts.tag_filter_label") }, FanboxUI.h("div", { class: "tag-filter-heading" }, FanboxUI.h("strong", {}, FanboxUI.t("posts.tag_filter_title")), FanboxUI.h("span", {}, actions.activeTag ? FanboxUI.t("posts.tag_current", { tag: actions.activeTag }) : FanboxUI.t("posts.tag_all_posts"))), FanboxUI.h("div", { class: "tag-filter-options" }, FanboxUI.h("button", { type: "button", class: actions.activeTag ? "" : "active",
            "aria-pressed": actions.activeTag ? "false" : "true", onclick: () => actions.onTag?.("") }, FanboxUI.t("posts.tag_all", { count: data.creator_total })), data.tag_facets.length ? data.tag_facets.map(facet => FanboxUI.h("button", {
            type: "button", class: actions.activeTag === facet.name ? "active" : "",
            "aria-pressed": actions.activeTag === facet.name ? "true" : "false",
            onclick: () => actions.onTag?.(facet.name),
        }, `${facet.name} ${facet.count}`)) : FanboxUI.h("span", { class: "tag-filter-empty" }, FanboxUI.t("posts.tag_none")))) : null;
        return FanboxUI.h("div", { class: "creator-posts" }, filter, actions.onOrder ? FanboxUI.h("div", { class: "list-toolbar" }, FanboxUI.sortToggle(actions.order ?? "desc", actions.onOrder, FanboxUI.t("posts.sort_label"))) : null, FanboxUI.h("div", { class: "post-list" }, cards.length ? cards : FanboxUI.h("p", { class: "empty" }, FanboxUI.t("posts.empty"))), renderPagination(data, actions.onPage, FanboxUI.t("posts.creator_pagination")));
    }
    FanboxUI.renderCreatorPostList = renderCreatorPostList;
    function richText(block) {
        const fragment = document.createDocumentFragment();
        const text = block.text ?? "";
        const styles = [...(block.styles ?? [])].sort((left, right) => left.offset - right.offset);
        let position = 0;
        for (const style of styles) {
            const start = Math.max(position, style.offset);
            if (start > position)
                fragment.append(text.slice(position, start));
            const end = Math.min(text.length, style.offset + style.length);
            fragment.append(FanboxUI.h("strong", {}, text.slice(start, end)));
            position = end;
        }
        if (position < text.length)
            fragment.append(text.slice(position));
        return fragment;
    }
    function embedView(block, onOpenPost) {
        const preview = block.embed;
        if (!preview || preview.kind !== "fanbox.post" || !preview.post_id) {
            if (!block.url)
                return null;
            return FanboxUI.h("p", { class: "attachment" }, FanboxUI.h("a", { href: block.url, target: "_blank", rel: "noreferrer" }, block.name || block.url));
        }
        const meta = [];
        if (preview.published_at)
            meta.push(FanboxUI.h("span", {}, FanboxUI.formatDate(preview.published_at)));
        if (preview.fee_required !== null && preview.fee_required !== undefined) {
            meta.push(FanboxUI.h("span", { class: "embed-fee" }, FanboxUI.feeLabel(preview.fee_required)));
        }
        if (preview.creator_name)
            meta.push(FanboxUI.h("span", {}, preview.creator_name));
        const attributes = preview.local_available
            ? { href: `#post-${preview.post_id}`, onclick: (event) => {
                    event.preventDefault();
                    onOpenPost(preview.post_id);
                } }
            : { href: preview.fanbox_url || "#", target: "_blank", rel: "noreferrer noopener" };
        return FanboxUI.h("a", { class: "embed-card", ...attributes }, FanboxUI.h("span", { class: "embed-content" }, FanboxUI.h("span", { class: "embed-source" }, preview.local_available ? FanboxUI.t("reader.embed_local") : FanboxUI.t("reader.embed_remote")), FanboxUI.h("strong", {}, preview.title || `Post ${preview.post_id}`), preview.excerpt ? FanboxUI.h("span", { class: "embed-excerpt" }, preview.excerpt) : null, FanboxUI.h("span", { class: "embed-meta" }, meta)), preview.cover_url
            ? FanboxUI.h("img", { class: "embed-cover", src: preview.cover_url, alt: "", loading: "lazy" })
            : FanboxUI.h("span", { class: "embed-cover placeholder", "aria-hidden": "true" }, "FANBOX"));
    }
    function blockView(block, onOpenPost) {
        if (block.type === "image" && block.media_url)
            return FanboxUI.h("figure", {}, FanboxUI.h("a", { href: block.media_url, target: "_blank" }, FanboxUI.h("img", { src: block.media_url, loading: "lazy", alt: block.name || FanboxUI.t("reader.image_alt") })));
        if (block.type === "file" && block.media_url)
            return FanboxUI.h("p", { class: "attachment" }, FanboxUI.h("a", { href: block.media_url }, block.name || block.filename || FanboxUI.t("reader.download_attachment")));
        if (block.type === "separator")
            return FanboxUI.h("hr");
        if (block.type === "quote")
            return FanboxUI.h("blockquote", {}, richText(block));
        if (block.type === "heading")
            return FanboxUI.h(`h${Math.min(Math.max(block.level || 2, 2), 6)}`, {}, richText(block));
        if (block.type === "embed")
            return embedView(block, onOpenPost);
        if (block.text)
            return FanboxUI.h("p", { class: "body-text" }, richText(block));
        return null;
    }
    function navigationView(navigation, placement, onOpenPost) {
        const control = (item, direction) => FanboxUI.h("button", {
            type: "button", class: `post-nav-button ${direction}`, disabled: !item,
            onclick: () => item && onOpenPost(item.post_id),
            title: item?.title || (direction === "previous" ? FanboxUI.t("reader.first_post") : FanboxUI.t("reader.last_post")),
        }, FanboxUI.h("span", {}, direction === "previous" ? FanboxUI.t("reader.previous") : FanboxUI.t("reader.next")), FanboxUI.h("strong", {}, item?.title || (direction === "previous" ? FanboxUI.t("reader.no_previous") : FanboxUI.t("reader.no_next"))));
        return FanboxUI.h("nav", {
            class: `post-navigation ${placement}`,
            "aria-label": placement === "top" ? FanboxUI.t("reader.nav_top") : FanboxUI.t("reader.nav_bottom"),
        }, control(navigation.previous, "previous"), FanboxUI.h("span", { class: "post-position" }, navigation.position ? `${navigation.position} / ${navigation.total}` : "—"), control(navigation.next, "next"));
    }
    function renderPostReader(post, actions) {
        const body = post.blocks
            .map(block => blockView(block, actions.onOpenPost))
            .filter((block) => block !== null);
        return FanboxUI.h("article", { class: "reader" }, FanboxUI.h("button", { type: "button", class: "back", onclick: actions.onBack }, FanboxUI.t("reader.back")), navigationView(post.navigation, "top", actions.onOpenPost), post.cover_url ? FanboxUI.h("a", { href: post.cover_url, target: "_blank" }, FanboxUI.h("img", { class: "cover", src: post.cover_url, alt: FanboxUI.t("reader.cover_alt") })) : null, FanboxUI.h("header", { class: "reader-heading" }, FanboxUI.h("p", { class: "eyebrow" }, `${post.creator_name} · POST ${post.post_id}`), FanboxUI.h("h1", {}, post.title), FanboxUI.h("div", { class: "reader-meta" }, post.is_pinned ? FanboxUI.h("span", { class: "pin-badge" }, FanboxUI.t("reader.pinned")) : null, FanboxUI.h("span", { class: "fee-badge" }, FanboxUI.feeLabel(post.fee_required)), FanboxUI.h("span", {}, FanboxUI.t("reader.published", { time: FanboxUI.formatDate(post.published_at) })), FanboxUI.h("span", {}, FanboxUI.t("reader.updated", { time: FanboxUI.formatDate(post.updated_at) }))), actions.versionSelect), FanboxUI.h("section", { class: "content" }, body.length ? body : FanboxUI.h("p", { class: "empty" }, FanboxUI.t("reader.empty_body"))), navigationView(post.navigation, "bottom", actions.onOpenPost), FanboxUI.h("footer", {}, FanboxUI.h("a", { href: post.url, target: "_blank", rel: "noreferrer" }, FanboxUI.t("reader.open_original"))));
    }
    FanboxUI.renderPostReader = renderPostReader;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function perkStatusClass(status) {
        const safeStatus = ["accessible", "inaccessible", "unavailable", "available", "unknown"].includes(status)
            ? status : "unknown";
        return `perk-status status-${safeStatus}`;
    }
    FanboxUI.perkStatusClass = perkStatusClass;
    function renderCreatorsPage(creators, query, onOpen) {
        const term = query.toLocaleLowerCase();
        const items = creators.filter(item => `${item.name} ${item.creator_id}`.toLocaleLowerCase().includes(term));
        const cards = items.map(item => FanboxUI.h("button", {
            type: "button", class: "creator-card", onclick: () => onOpen(item.creator_id),
        }, item.avatar_url
            ? FanboxUI.h("img", { src: item.avatar_url, alt: "", loading: "lazy" })
            : FanboxUI.h("span", { class: "avatar" }, item.name.slice(0, 1)), FanboxUI.h("span", { class: "post-main" }, FanboxUI.h("strong", {}, item.name), FanboxUI.h("small", {}, FanboxUI.t("creators.card_meta", { creator_id: item.creator_id, count: item.post_count }))), FanboxUI.h("span", { class: `badge status-${item.status}` }, item.status)));
        return FanboxUI.h("section", { class: "page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, FanboxUI.t("creators.eyebrow")), FanboxUI.h("h1", {}, FanboxUI.t("creators.title")), FanboxUI.h("p", {}, FanboxUI.t("creators.matching", { count: items.length })))), FanboxUI.h("div", { class: "creator-grid" }, cards.length ? cards : FanboxUI.h("p", { class: "empty" }, FanboxUI.t("creators.empty"))));
    }
    FanboxUI.renderCreatorsPage = renderCreatorsPage;
    function renderCreatorShell(creator, tab, content, profile, actions) {
        const tabs = [
            ["profile", FanboxUI.t("creator.tab_profile"), "PROFILE"], ["posts", FanboxUI.t("creator.tab_posts"), "POSTS"],
            ["fancards", FanboxUI.t("creator.tab_fancards"), "FAN CARD"],
        ];
        return FanboxUI.h("section", { class: "page creator-page", "data-creator-id": creator.creator_id }, FanboxUI.h("button", { type: "button", class: "back", onclick: actions.onBack }, FanboxUI.t("creator.back")), FanboxUI.h("header", { class: `creator-hero${profile?.cover_url ? " has-cover" : ""}` }, profile?.cover_url ? FanboxUI.h("img", { class: "creator-cover", src: profile.cover_url, alt: "" }) : null, creator.avatar_url
            ? FanboxUI.h("img", { src: creator.avatar_url, alt: "" })
            : FanboxUI.h("span", { class: "avatar large" }, creator.name.slice(0, 1)), FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, `@${creator.creator_id}`), FanboxUI.h("h1", {}, creator.name), FanboxUI.h("p", {}, FanboxUI.t("creator.hero_meta", { posts: creator.post_count, cards: creator.fancard_count }))), FanboxUI.h("a", { class: "external-button", href: creator.fanbox_url, target: "_blank", rel: "noreferrer" }, FanboxUI.t("creator.open_fanbox"))), FanboxUI.h("nav", { class: "subnav", "aria-label": FanboxUI.t("creator.nav_label") }, tabs.map(([key, zh, en]) => FanboxUI.h("button", {
            type: "button", class: key === tab ? "active" : "", "data-creator-tab": key,
            onclick: () => actions.onTab(key),
        }, FanboxUI.h("strong", {}, zh), FanboxUI.h("small", {}, en)))), FanboxUI.h("div", { class: "creator-content", "aria-live": "polite" }, content));
    }
    FanboxUI.renderCreatorShell = renderCreatorShell;
    function renderCreatorProfile(creator, profile, versionSelect) {
        const safeLinks = (profile?.profile_items ?? []).filter(item => item.url?.startsWith("https://"));
        const profileImages = (profile?.profile_items ?? []).filter(item => item.image_url);
        return FanboxUI.h("div", { class: "profile-layout" }, !profile ? FanboxUI.h("section", { class: "profile-empty" }, FanboxUI.h("p", { class: "eyebrow" }, "PROFILE ARCHIVE"), FanboxUI.h("h2", {}, FanboxUI.t("profile.empty_title")), FanboxUI.h("p", {}, FanboxUI.t("profile.empty_body"))) : null, profile ? FanboxUI.h("section", { class: "info-panel profile-about" }, FanboxUI.h("p", { class: "eyebrow" }, "ABOUT"), FanboxUI.h("h2", {}, FanboxUI.t("profile.about_title")), profileImages.length ? FanboxUI.h("div", { class: "profile-gallery", "aria-label": FanboxUI.t("profile.gallery_label") }, profileImages.map((item, index) => FanboxUI.h("a", { href: item.image_url, target: "_blank" }, FanboxUI.h("img", { src: item.image_url, alt: item.label || FanboxUI.t("profile.image_alt", { number: index + 1 }), loading: "lazy" })))) : null, profile.description ? FanboxUI.h("p", { class: "body-text" }, profile.description)
            : FanboxUI.h("p", { class: "profile-about-empty" }, FanboxUI.t("profile.about_empty"))) : null, safeLinks.length ? FanboxUI.h("section", { class: "info-panel profile-links" }, FanboxUI.h("p", { class: "eyebrow" }, "LINKS"), FanboxUI.h("h2", {}, FanboxUI.t("profile.links_title")), FanboxUI.h("div", { class: "link-grid" }, safeLinks.map(item => FanboxUI.h("a", {
            href: item.url, target: "_blank", rel: "noreferrer",
        }, FanboxUI.h("strong", {}, item.label || item.type || FanboxUI.t("profile.link_fallback")), item.description ? FanboxUI.h("span", {}, item.description) : null)))) : null, profile ? FanboxUI.h("section", { class: "info-panel profile-meta" }, FanboxUI.h("p", { class: "eyebrow" }, "ARCHIVE METADATA"), FanboxUI.h("h2", {}, FanboxUI.t("profile.meta_title")), FanboxUI.h("div", { class: "status-list" }, profile.has_adult_content ? FanboxUI.h("span", { class: "profile-flag adult" }, FanboxUI.t("profile.adult")) : FanboxUI.h("span", { class: "profile-flag" }, FanboxUI.t("profile.general")), FanboxUI.h("span", { class: "profile-flag" }, profile.is_accepting_request ? FanboxUI.t("profile.accepting") : FanboxUI.t("profile.not_accepting")), profile.is_stopped ? FanboxUI.h("span", { class: "profile-flag danger" }, FanboxUI.t("profile.stopped")) : FanboxUI.h("span", { class: "profile-flag" }, FanboxUI.t("profile.active"))), FanboxUI.h("dl", {}, FanboxUI.h("div", {}, FanboxUI.h("dt", {}, FanboxUI.t("profile.captured_at")), FanboxUI.h("dd", {}, FanboxUI.formatDate(profile.captured_at))), FanboxUI.h("div", {}, FanboxUI.h("dt", {}, FanboxUI.t("common.version")), FanboxUI.h("dd", {}, versionSelect)))) : null, FanboxUI.h("section", { class: "profile-stats" }, FanboxUI.h("div", {}, FanboxUI.h("strong", {}, creator.post_count), FanboxUI.h("span", {}, FanboxUI.t("profile.stat_posts"))), FanboxUI.h("div", {}, FanboxUI.h("strong", {}, creator.completed_count), FanboxUI.h("span", {}, FanboxUI.t("profile.stat_completed"))), FanboxUI.h("div", {}, FanboxUI.h("strong", {}, creator.fancard_count), FanboxUI.h("span", {}, FanboxUI.t("profile.stat_fancards")))));
    }
    FanboxUI.renderCreatorProfile = renderCreatorProfile;
    function renderFanCardList(data, actions) {
        const cards = data.items.map(item => FanboxUI.h("button", {
            type: "button", class: "fancard-card", onclick: () => actions.onOpen(item.creator_id, item.target_month),
        }, item.image_url
            ? FanboxUI.h("img", { src: item.image_url, alt: FanboxUI.t("fancards.image_alt", { creator: item.creator_name }), loading: "lazy" })
            : FanboxUI.h("div", { class: "card-placeholder" }, FanboxUI.t("fancards.no_image")), FanboxUI.h("span", { class: "post-main" }, FanboxUI.h("span", { class: "eyebrow" }, item.target_month), FanboxUI.h("strong", {}, item.plan_title || FanboxUI.t("fancards.plan_untitled")), FanboxUI.h("small", {}, FanboxUI.t("fancards.card_meta", { fee: FanboxUI.feeLabel(item.fee), count: item.version_count })))));
        return FanboxUI.h("div", { class: "fancard-grid" }, cards.length ? cards : FanboxUI.h("p", { class: "empty" }, FanboxUI.t("fancards.empty")));
    }
    FanboxUI.renderFanCardList = renderFanCardList;
    function renderFanCardReader(card, actions) {
        const perks = card.perks.length ? FanboxUI.h("section", { class: "perk-section" }, FanboxUI.h("p", { class: "eyebrow" }, "PLAN BENEFITS"), FanboxUI.h("h2", {}, FanboxUI.t("fancard.perks_title")), FanboxUI.h("div", { class: "perk-grid" }, card.perks.map(perk => FanboxUI.h("article", { class: "perk-card" }, FanboxUI.h("div", { class: "perk-card-heading" }, FanboxUI.h("h3", {}, perk.label), FanboxUI.h("span", { class: perkStatusClass(perk.status) }, perk.status_label)), FanboxUI.h("p", {}, perk.description), perk.guidance ? FanboxUI.h("p", { class: "perk-guidance" }, perk.guidance, " ", perk.settings_url ? FanboxUI.h("a", { href: perk.settings_url, target: "_blank", rel: "noreferrer" }, `${perk.settings_label || FanboxUI.t("fancard.account_settings")} ↗`) : null) : null, perk.action_url && perk.action_label ? FanboxUI.h("a", {
            class: "perk-action", href: perk.action_url, target: "_blank", rel: "noreferrer",
        }, `${perk.action_label} ↗`) : null)))) : null;
        return FanboxUI.h("article", { class: "reader fancard-reader" }, FanboxUI.h("button", { type: "button", class: "back", onclick: actions.onBack }, FanboxUI.t("fancard.back")), card.image_url
            ? FanboxUI.h("a", { href: card.image_url, target: "_blank" }, FanboxUI.h("img", { class: "card-image", src: card.image_url, alt: FanboxUI.t("fancards.image_alt", { creator: card.creator_name }) }))
            : FanboxUI.h("div", { class: "card-placeholder large" }, FanboxUI.t("fancard.no_custom_image")), FanboxUI.h("header", { class: "reader-heading" }, FanboxUI.h("p", { class: "eyebrow" }, `${card.target_month} · ${card.creator_id}`), FanboxUI.h("h1", {}, card.creator_name), FanboxUI.h("p", {}, FanboxUI.t("fancard.plan_line", { plan: card.plan_title || FanboxUI.t("fancards.plan_untitled"), fee: FanboxUI.feeLabel(card.fee) })), actions.versionSelect), FanboxUI.h("section", { class: "content" }, FanboxUI.h("h2", {}, FanboxUI.t("fancard.plan_info")), FanboxUI.h("p", { class: "body-text" }, card.description || FanboxUI.t("fancard.no_description")), card.support_start ? FanboxUI.h("p", {}, FanboxUI.t("fancard.support_start", { time: FanboxUI.formatDate(card.support_start) })) : null, card.support_months.length ? FanboxUI.h("p", {}, FanboxUI.t("fancard.saved_months", { months: card.support_months.join(FanboxUI.t("fancard.month_separator")) })) : null, perks));
    }
    FanboxUI.renderFanCardReader = renderFanCardReader;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function lastResultText(status) {
        const job = status.last_job;
        if (!job)
            return status.last_due_at ? FanboxUI.t("schedule.last_due", { time: FanboxUI.formatDate(status.last_due_at) }) : FanboxUI.t("schedule.never_run");
        const outcome = job.status === "completed" ? FanboxUI.t("schedule.outcome_completed")
            : job.status === "failed" ? FanboxUI.t("schedule.outcome_failed")
                : FanboxUI.isActiveJob(job) ? FanboxUI.t("schedule.outcome_running") : FanboxUI.statusText(job.status);
        const time = FanboxUI.formatDate(status.last_due_at ?? job.created_at);
        return job.error ? FanboxUI.t("schedule.last_result_error", { time, outcome, error: job.error })
            : FanboxUI.t("schedule.last_result", { time, outcome });
    }
    function renderScheduleSection(value, status, creators, blocked, actions) {
        const enabled = FanboxUI.h("input", { type: "checkbox", checked: value.enabled });
        let frequencyValue = value.frequency;
        let powerValue = value.power;
        let monthDay = value.month_day;
        const interval = FanboxUI.h("input", { type: "number", value: value.interval, min: 1, max: 30, step: 1 });
        const [savedHour, savedMinute] = value.time.split(":");
        const hour = FanboxUI.customSelect({ id: "schedule-hour", label: FanboxUI.t("schedule.hour"), value: savedHour, disabled: blocked,
            options: Array.from({ length: 24 }, (_, index) => ({ value: String(index).padStart(2, "0"), label: String(index).padStart(2, "0") })),
            onChange: () => sync() });
        const minute = FanboxUI.customSelect({ id: "schedule-minute", label: FanboxUI.t("schedule.minute"), value: savedMinute, disabled: blocked,
            options: Array.from({ length: 60 }, (_, index) => ({ value: String(index).padStart(2, "0"), label: String(index).padStart(2, "0") })),
            onChange: () => sync() });
        const intervalUnit = FanboxUI.h("small", {});
        const preview = FanboxUI.h("p", { class: "schedule-preview", role: "status", "aria-live": "polite" });
        const runFeedback = FanboxUI.h("p", { class: "settings-error", role: "alert", hidden: true });
        const frequency = FanboxUI.customSelect({ id: "schedule-frequency", label: FanboxUI.t("schedule.frequency"), value: frequencyValue, disabled: blocked,
            options: [{ value: "daily", label: FanboxUI.t("schedule.frequency_daily") }, { value: "weekly", label: FanboxUI.t("schedule.frequency_weekly") },
                { value: "monthly", label: FanboxUI.t("schedule.frequency_monthly") }],
            onChange: next => { frequencyValue = next; sync(); } });
        const power = FanboxUI.customSelect({ id: "schedule-power", label: FanboxUI.t("schedule.power"), value: powerValue, disabled: blocked,
            options: [{ value: "no_wake_battery_ok", label: FanboxUI.t("schedule.power_no_wake_battery_ok") },
                { value: "no_wake_ac_only", label: FanboxUI.t("schedule.power_no_wake_ac_only") },
                { value: "wake", label: FanboxUI.t("schedule.power_wake") }],
            onChange: next => { powerValue = next; sync(); } });
        const weekday = FanboxUI.customSelect({ id: "schedule-weekday", label: FanboxUI.t("schedule.weekday"), value: value.weekday, disabled: blocked,
            options: Array.from({ length: 7 }, (_, index) => ({ value: index, label: FanboxUI.t(`schedule.weekday_${index}`) })),
            onChange: () => sync() });
        const dayButtons = Array.from({ length: 31 }, (_, index) => FanboxUI.h("button", { type: "button",
            class: "schedule-day", "aria-pressed": index + 1 === monthDay ? "true" : "false",
            onclick: () => { monthDay = index + 1; sync(); } }, String(index + 1)));
        const creatorBoxes = creators.map(item => {
            const input = FanboxUI.h("input", { type: "checkbox", value: item.creator_id,
                checked: value.creators.includes(item.creator_id) });
            input.addEventListener("change", () => sync());
            return { input, node: FanboxUI.h("label", { class: "setting-toggle" }, input, FanboxUI.h("span", {}, `${item.name} @${item.creator_id}`)) };
        });
        const unknownCreators = value.creators.filter(id => !creators.some(item => item.creator_id === id));
        const intervalField = FanboxUI.h("label", { class: "setting-field" }, FanboxUI.h("span", {}, FanboxUI.t("schedule.interval")), interval, intervalUnit);
        const weekdayField = FanboxUI.h("div", { class: "setting-field" }, FanboxUI.h("span", {}, FanboxUI.t("schedule.weekday")), weekday);
        const monthField = FanboxUI.h("div", { class: "setting-field schedule-month" }, FanboxUI.h("span", { id: "schedule-month-label" }, FanboxUI.t("schedule.month_day")), FanboxUI.h("div", { class: "schedule-days", role: "group", "aria-labelledby": "schedule-month-label" }, dayButtons), FanboxUI.h("small", {}, FanboxUI.t("schedule.month_day_hint")));
        const read = () => ({
            enabled: enabled.checked, frequency: frequencyValue,
            interval: Math.min(30, Math.max(1, Math.round(Number(interval.value) || 1))),
            weekday: Number(weekday.value), month_day: monthDay, time: `${hour.value}:${minute.value}`, power: powerValue,
            creators: [...creatorBoxes.filter(item => item.input.checked).map(item => item.input.value), ...unknownCreators],
        });
        let previewTimer;
        let previewToken = 0;
        const sync = () => {
            intervalField.hidden = frequencyValue === "monthly";
            weekdayField.hidden = frequencyValue !== "weekly";
            monthField.hidden = frequencyValue !== "monthly";
            intervalUnit.textContent = FanboxUI.t(frequencyValue === "weekly" ? "schedule.interval_weekly" : "schedule.interval_daily");
            for (const [index, button] of dayButtons.entries()) {
                button.setAttribute("aria-pressed", index + 1 === monthDay ? "true" : "false");
            }
            if (previewTimer !== undefined)
                clearTimeout(previewTimer);
            previewTimer = window.setTimeout(() => {
                const token = ++previewToken;
                actions.onPreview(read()).then(result => {
                    if (token !== previewToken)
                        return;
                    preview.textContent = FanboxUI.t("schedule.preview", { summary: result.summary,
                        runs: result.next_runs.map(FanboxUI.formatDate).join(FanboxUI.t("schedule.run_separator")) });
                }).catch(error => {
                    if (token !== previewToken)
                        return;
                    preview.textContent = FanboxUI.t("schedule.preview_failed", { error: error instanceof Error ? error.message : String(error) });
                });
            }, 250);
        };
        for (const input of [enabled, interval])
            input.addEventListener("input", sync);
        const runNow = FanboxUI.h("button", { type: "button", class: "secondary", disabled: blocked, onclick: async () => {
                runFeedback.hidden = true;
                const error = await actions.onRunNow();
                if (error) {
                    runFeedback.textContent = error;
                    runFeedback.hidden = false;
                }
            } }, FanboxUI.t("schedule.run_now"));
        const runBlockedNote = FanboxUI.h("small", { class: "schedule-run-blocked", hidden: true });
        const enabledField = FanboxUI.h("label", { class: "setting-toggle" }, enabled, FanboxUI.h("span", {}, FanboxUI.t("schedule.enabled")));
        const frequencyField = FanboxUI.h("div", { class: "setting-field" }, FanboxUI.h("span", {}, FanboxUI.t("schedule.frequency")), frequency);
        const timeField = FanboxUI.h("div", { class: "setting-field" }, FanboxUI.h("span", {}, FanboxUI.t("schedule.time", { zone: status.timezone })), FanboxUI.h("div", { class: "schedule-time" }, hour, FanboxUI.h("span", { "aria-hidden": "true" }, ":"), minute));
        const powerField = FanboxUI.h("div", { class: "setting-field schedule-power" }, FanboxUI.h("span", {}, FanboxUI.t("schedule.power")), power, FanboxUI.h("small", {}, FanboxUI.t("schedule.power_hint")));
        const creatorsField = FanboxUI.h("details", { class: "schedule-creators" }, FanboxUI.h("summary", {}, FanboxUI.t("schedule.creators_summary")), creatorBoxes.length ? FanboxUI.h("div", { class: "setting-toggles" }, creatorBoxes.map(item => item.node))
            : FanboxUI.h("p", { class: "settings-section-description" }, FanboxUI.t("schedule.creators_empty")));
        const node = FanboxUI.h("section", { class: "settings-section schedule-settings" }, FanboxUI.h("h3", {}, FanboxUI.t("schedule.title")), FanboxUI.h("p", { class: "settings-section-description" }, FanboxUI.t("schedule.description", { zone: status.timezone })), FanboxUI.h("dl", { class: "schedule-status" }, FanboxUI.h("div", {}, FanboxUI.h("dt", {}, FanboxUI.t("schedule.current")), FanboxUI.h("dd", {}, status.enabled ? status.summary : FanboxUI.t("schedule.disabled"))), FanboxUI.h("div", {}, FanboxUI.h("dt", {}, FanboxUI.t("schedule.next_run")), FanboxUI.h("dd", {}, status.next_run_at ? FanboxUI.formatDate(status.next_run_at) : "—")), FanboxUI.h("div", {}, FanboxUI.h("dt", {}, FanboxUI.t("schedule.last_result_label")), FanboxUI.h("dd", {}, lastResultText(status))), FanboxUI.h("div", { class: `schedule-background state-${status.background.state}` }, FanboxUI.h("dt", {}, FanboxUI.t("schedule.background")), FanboxUI.h("dd", {}, status.background.message))), status.note ? FanboxUI.h("p", { class: "notice schedule-note" }, status.note) : null, enabledField, FanboxUI.h("div", { class: "settings-grid" }, frequencyField, intervalField, weekdayField, timeField), monthField, powerField, creatorsField, preview, FanboxUI.h("div", { class: "schedule-actions" }, runNow, FanboxUI.h("span", { class: "settings-section-description" }, FanboxUI.t("schedule.run_now_hint")), runBlockedNote), runFeedback);
        sync();
        const fields = [
            { node: enabledField, read: () => read().enabled },
            { node: frequencyField, read: () => read().frequency },
            { node: intervalField, read: () => read().interval },
            { node: weekdayField, read: () => read().weekday },
            { node: timeField, read: () => read().time },
            { node: monthField, read: () => read().month_day },
            { node: powerField, read: () => read().power },
            { node: creatorsField, read: () => read().creators },
        ];
        let locked = blocked;
        let runReason = null;
        const updateRun = () => {
            runNow.disabled = locked || runReason !== null;
            runBlockedNote.hidden = runReason === null;
            runBlockedNote.textContent = runReason ?? "";
        };
        const setRunBlocked = (reason) => { runReason = reason; updateRun(); };
        const setLocked = (next) => { locked = next; updateRun(); };
        return { node, read, fields, setRunBlocked, setLocked };
    }
    FanboxUI.renderScheduleSection = renderScheduleSection;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    const NAMED_COLORS = ["bg", "surface", "surface-2", "text", "muted", "line", "accent", "accent-soft",
        "blue", "green", "yellow", "red", "purple"];
    const colorLabel = (key) => NAMED_COLORS.includes(key) ? FanboxUI.t(`colors.${key.replace("-", "_")}`) : key;
    const modeLabel = (mode) => FanboxUI.t(`colors.mode_${mode}`);
    const HEX_COLOR = /^#[0-9a-f]{6}$/;
    const EXPORT_FORMAT = "fanbox-archiver-colors";
    const CONTRAST_CHECKS = [
        ["text", "bg", 4.5, "colors.pair_text_bg"], ["text", "surface", 4.5, "colors.pair_text_surface"],
        ["text", "surface-2", 4.5, "colors.pair_text_surface_2"], ["muted", "surface", 3, "colors.pair_muted_surface"],
        ["accent", "surface", 3, "colors.pair_accent_surface"], ["white", "accent", 3, "colors.pair_white_accent"],
        ["red", "surface", 3, "colors.pair_red_surface"], ["green", "surface", 3, "colors.pair_green_surface"],
    ];
    function hexToRgb(hex) {
        const value = Number.parseInt(hex.slice(1), 16);
        return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
    }
    function rgbToHex(r, g, b) {
        return `#${[r, g, b].map(part => Math.round(Math.min(255, Math.max(0, part))).toString(16).padStart(2, "0")).join("")}`;
    }
    function rgbToHsl(r, g, b) {
        const [red, green, blue] = [r / 255, g / 255, b / 255];
        const max = Math.max(red, green, blue), min = Math.min(red, green, blue);
        const lightness = (max + min) / 2;
        if (max === min)
            return [0, 0, Math.round(lightness * 100)];
        const delta = max - min;
        const saturation = lightness > .5 ? delta / (2 - max - min) : delta / (max + min);
        const hue = max === red ? (green - blue) / delta + (green < blue ? 6 : 0)
            : max === green ? (blue - red) / delta + 2 : (red - green) / delta + 4;
        return [Math.round(hue * 60), Math.round(saturation * 100), Math.round(lightness * 100)];
    }
    function hslToRgb(h, s, l) {
        const saturation = s / 100, lightness = l / 100;
        const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
        const segment = (h % 360) / 60;
        const second = chroma * (1 - Math.abs(segment % 2 - 1));
        const [r, g, b] = segment < 1 ? [chroma, second, 0] : segment < 2 ? [second, chroma, 0]
            : segment < 3 ? [0, chroma, second] : segment < 4 ? [0, second, chroma]
                : segment < 5 ? [second, 0, chroma] : [chroma, 0, second];
        const offset = lightness - chroma / 2;
        return [(r + offset) * 255, (g + offset) * 255, (b + offset) * 255];
    }
    function contrastRatio(first, second) {
        const luminance = (hex) => {
            const [r, g, b] = hexToRgb(hex).map(part => {
                const channel = part / 255;
                return channel <= .03928 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
            });
            return .2126 * r + .7152 * g + .0722 * b;
        };
        const [light, dark] = [luminance(first), luminance(second)].sort((a, b) => b - a);
        return (light + .05) / (dark + .05);
    }
    FanboxUI.contrastRatio = contrastRatio;
    function parseColorExport(text, keys) {
        let value;
        try {
            value = JSON.parse(text);
        }
        catch {
            throw new Error(FanboxUI.t("colors.invalid_json"));
        }
        if (!value || typeof value !== "object" || value.format !== EXPORT_FORMAT) {
            throw new Error(FanboxUI.t("colors.not_export"));
        }
        const result = { light: {}, dark: {} };
        for (const mode of ["light", "dark"]) {
            const colors = value[mode] ?? {};
            if (typeof colors !== "object" || colors === null)
                throw new Error(FanboxUI.t("colors.mode_invalid", { mode: modeLabel(mode) }));
            for (const [key, color] of Object.entries(colors)) {
                if (!keys.includes(key))
                    throw new Error(FanboxUI.t("colors.unknown_key", { key }));
                const normalized = String(color).trim().toLowerCase();
                if (!HEX_COLOR.test(normalized))
                    throw new Error(FanboxUI.t("colors.invalid_hex", { key }));
                result[mode][key] = normalized;
            }
        }
        return result;
    }
    FanboxUI.parseColorExport = parseColorExport;
    function copy(colors) {
        return { light: { ...colors.light }, dark: { ...colors.dark } };
    }
    function numberSlider(label, max, onValue) {
        const range = FanboxUI.h("input", { type: "range", min: 0, max, step: 1, "aria-label": label });
        const number = FanboxUI.h("input", { type: "number", min: 0, max, step: 1, "aria-label": FanboxUI.t("colors.slider_value", { label }) });
        const emit = (source) => {
            const value = Math.min(max, Math.max(0, Math.round(Number(source.value) || 0)));
            (source === range ? number : range).value = String(value);
            onValue(value);
        };
        range.addEventListener("input", () => emit(range));
        number.addEventListener("change", () => emit(number));
        return { node: FanboxUI.h("label", { class: "color-slider" }, FanboxUI.h("span", {}, label), range, number),
            set(value) { range.value = String(value); number.value = String(value); } };
    }
    function colorEditor(data) {
        const keys = data.theme_colors.keys;
        const defaults = data.theme_colors.defaults;
        const saved = copy(data.editable.display.colors);
        let working = copy(saved);
        const theme = data.editable.display.theme;
        let mode = theme === "system"
            ? (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme;
        const effective = (key) => working[mode][key] ?? defaults[mode][key] ?? "#000000";
        const feedback = FanboxUI.h("p", { class: "color-feedback", role: "status", "aria-live": "polite" });
        const warnings = FanboxUI.h("ul", { class: "color-warnings" });
        const preview = FanboxUI.h("div", { class: "color-preview", "aria-label": FanboxUI.t("colors.preview_label") }, FanboxUI.h("div", { class: "color-preview-card" }, FanboxUI.h("strong", {}, FanboxUI.t("colors.preview_title")), FanboxUI.h("p", {}, FanboxUI.t("colors.preview_text")), FanboxUI.h("p", { class: "color-preview-muted" }, FanboxUI.t("colors.preview_muted")), FanboxUI.h("div", { class: "color-preview-row" }, FanboxUI.h("span", { class: "color-preview-button" }, FanboxUI.t("colors.preview_button")), FanboxUI.h("span", { class: "color-preview-chip" }, FanboxUI.t("colors.preview_chip")), FanboxUI.h("span", { class: "color-preview-link" }, FanboxUI.t("colors.preview_link"))), FanboxUI.h("div", { class: "color-preview-row" }, ...["blue", "green", "yellow", "red", "purple"].map(key => FanboxUI.h("span", { class: "color-preview-status", "data-color": key }, colorLabel(key))))));
        const rows = FanboxUI.h("div", { class: "color-rows" });
        const modeButtons = ["light", "dark"].map(value => FanboxUI.h("button", { type: "button",
            class: "color-mode", "aria-pressed": value === mode,
            onclick: () => { mode = value; render(); } }, modeLabel(value)));
        function refreshPreview() {
            for (const key of keys)
                preview.style.setProperty(`--${key}`, effective(key));
            warnings.replaceChildren(...CONTRAST_CHECKS.flatMap(([foreground, background, minimum, labelKey]) => {
                const ratio = contrastRatio(foreground === "white" ? "#ffffff" : effective(foreground), effective(background));
                return ratio < minimum
                    ? [FanboxUI.h("li", {}, FanboxUI.t("colors.contrast_warning", { label: FanboxUI.t(labelKey), ratio: ratio.toFixed(2), minimum: String(minimum) }))] : [];
            }));
            warnings.hidden = !warnings.childElementCount;
        }
        function colorRow(key) {
            const swatch = FanboxUI.h("span", { class: "color-swatch", "aria-hidden": "true" });
            const code = FanboxUI.h("code", {});
            const badge = FanboxUI.h("small", { class: "color-badge" });
            const hex = FanboxUI.h("input", { type: "text", maxlength: 7, spellcheck: "false", autocomplete: "off",
                "aria-label": FanboxUI.t("colors.hex_label", { label: colorLabel(key) }), class: "color-hex" });
            let current = effective(key);
            const setColor = (value, source) => {
                current = value;
                if (value === defaults[mode][key])
                    delete working[mode][key];
                else
                    working[mode][key] = value;
                update(source);
                refreshPreview();
            };
            const fromRgb = (index) => (value) => {
                const rgb = hexToRgb(current);
                rgb[index] = value;
                setColor(rgbToHex(...rgb), "rgb");
            };
            const fromHsl = (index) => (value) => {
                const hsl = rgbToHsl(...hexToRgb(current));
                hsl[index] = value;
                setColor(rgbToHex(...hslToRgb(...hsl)), "hsl");
            };
            const rgb = ["R", "G", "B"].map((label, index) => numberSlider(label, 255, fromRgb(index)));
            const hsl = [[FanboxUI.t("colors.hue"), 360], [FanboxUI.t("colors.saturation"), 100], [FanboxUI.t("colors.lightness"), 100]].map(([label, max], index) => numberSlider(label, max, fromHsl(index)));
            function update(source) {
                swatch.style.background = current;
                code.textContent = current;
                badge.textContent = working[mode][key] ? FanboxUI.t("colors.badge_custom") : FanboxUI.t("colors.badge_default");
                badge.classList.toggle("custom", Boolean(working[mode][key]));
                if (source !== "hex") {
                    hex.value = current;
                    hex.removeAttribute("aria-invalid");
                }
                if (source !== "rgb")
                    hexToRgb(current).forEach((value, index) => rgb[index]?.set(value));
                if (source !== "hsl")
                    rgbToHsl(...hexToRgb(current)).forEach((value, index) => hsl[index]?.set(value));
            }
            hex.addEventListener("input", () => {
                const value = hex.value.trim().toLowerCase();
                const normalized = value.startsWith("#") ? value : `#${value}`;
                if (HEX_COLOR.test(normalized))
                    setColor(normalized, "hex");
                else
                    hex.setAttribute("aria-invalid", "true");
            });
            hex.addEventListener("blur", () => update());
            update();
            return FanboxUI.h("details", { class: "color-row" }, FanboxUI.h("summary", {}, swatch, FanboxUI.h("span", { class: "color-name" }, colorLabel(key)), code, badge), FanboxUI.h("div", { class: "color-controls" }, FanboxUI.h("label", { class: "color-hex-field" }, FanboxUI.h("span", {}, "Hex"), hex), FanboxUI.h("div", { class: "color-slider-group" }, FanboxUI.h("span", { class: "color-group-label" }, "RGB"), ...rgb.map(item => item.node)), FanboxUI.h("div", { class: "color-slider-group" }, FanboxUI.h("span", { class: "color-group-label" }, FanboxUI.t("colors.hsl_group")), ...hsl.map(item => item.node)), FanboxUI.h("button", { type: "button", onclick: () => setColor(defaults[mode][key] ?? current) }, FanboxUI.t("colors.reset_color"))));
        }
        function render() {
            modeButtons.forEach((button, index) => button.setAttribute("aria-pressed", String(["light", "dark"][index] === mode)));
            preview.dataset.mode = mode;
            rows.replaceChildren(...keys.map(colorRow));
            refreshPreview();
        }
        const importInput = FanboxUI.h("input", { type: "file", accept: "application/json,.json", hidden: true,
            onchange: async (event) => {
                const input = event.currentTarget;
                const file = input.files?.[0];
                input.value = "";
                if (!file)
                    return;
                try {
                    working = parseColorExport(await file.text(), keys);
                    render();
                    feedback.textContent = FanboxUI.t("colors.imported");
                }
                catch (error) {
                    feedback.textContent = FanboxUI.t("colors.import_failed", { error: error instanceof Error ? error.message : String(error) });
                }
            } });
        const node = FanboxUI.h("section", { class: "settings-section color-editor" }, FanboxUI.h("h3", {}, FanboxUI.t("colors.title")), FanboxUI.h("p", { class: "settings-section-description" }, FanboxUI.t("colors.description")), FanboxUI.h("div", { class: "color-mode-switch", role: "group", "aria-label": FanboxUI.t("colors.mode_switch_label") }, ...modeButtons), preview, warnings, rows, FanboxUI.h("div", { class: "color-actions" }, FanboxUI.h("button", { type: "button", onclick: () => {
                working[mode] = {};
                render();
                feedback.textContent = FanboxUI.t("colors.mode_reset", { mode: modeLabel(mode) });
            } }, FanboxUI.t("colors.reset_mode")), FanboxUI.h("button", { type: "button", onclick: () => { working = copy(saved); render(); feedback.textContent = FanboxUI.t("colors.discarded"); } }, FanboxUI.t("colors.discard")), FanboxUI.h("button", { type: "button", onclick: () => {
                const blob = new Blob([JSON.stringify({ format: EXPORT_FORMAT, version: 1, ...working }, null, 2) + "\n"], { type: "application/json" });
                const url = URL.createObjectURL(blob);
                const link = FanboxUI.h("a", { href: url, download: "fanbox-archiver-colors.json", hidden: true });
                document.body.append(link);
                link.click();
                link.remove();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
                feedback.textContent = FanboxUI.t("colors.exported");
            } }, FanboxUI.t("colors.export")), FanboxUI.h("button", { type: "button", onclick: () => importInput.click() }, FanboxUI.t("colors.import")), importInput), feedback);
        render();
        return { node, read: () => copy(working) };
    }
    FanboxUI.colorEditor = colorEditor;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function settingCheckbox(label, checked) {
        const input = FanboxUI.h("input", { type: "checkbox", checked });
        return { input, node: FanboxUI.h("label", { class: "setting-toggle" }, input, FanboxUI.h("span", {}, label)) };
    }
    function settingNumber(label, value, min, max, step = 1, hint = null) {
        const input = FanboxUI.h("input", { type: "number", value, min, max, step });
        return { input, node: FanboxUI.h("label", { class: "setting-field" }, FanboxUI.h("span", {}, label), input, hint ? FanboxUI.h("small", {}, hint) : null) };
    }
    const OTHER_TIMEZONE = "__other__";
    function timezoneControl(data, blocked) {
        const setting = data.editable.display.timezone;
        const common = data.timezones.common;
        const custom = setting !== "system" && !common.includes(setting);
        let choice = custom ? OTHER_TIMEZONE : setting;
        const listId = `timezone-list-${Math.random().toString(36).slice(2, 9)}`;
        const other = FanboxUI.h("input", { type: "text", value: custom ? setting : "", list: listId, spellcheck: "false",
            placeholder: FanboxUI.t("settings.timezone_placeholder"), "aria-label": FanboxUI.t("settings.timezone_other_aria"), autocomplete: "off" });
        const otherField = FanboxUI.h("label", { class: "setting-field timezone-other", hidden: !custom }, FanboxUI.h("span", {}, FanboxUI.t("settings.timezone_other_search")), other, FanboxUI.h("datalist", { id: listId }, data.timezones.all.map(name => FanboxUI.h("option", { value: name }))));
        const select = FanboxUI.customSelect({ id: "display-timezone", label: FanboxUI.t("settings.timezone"), value: choice, disabled: blocked,
            options: [{ value: "system", label: FanboxUI.t("settings.timezone_system", { zone: data.display.system_timezone }) },
                ...common.map(name => ({ value: name, label: name })), { value: OTHER_TIMEZONE, label: FanboxUI.t("settings.timezone_other") }],
            onChange: next => { choice = next; otherField.hidden = next !== OTHER_TIMEZONE; if (!otherField.hidden)
                other.focus(); } });
        const node = FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, FanboxUI.t("settings.timezone")), FanboxUI.h("p", { class: "settings-section-description" }, FanboxUI.t("settings.timezone_description", { zone: data.display.timezone })), data.display.notice ? FanboxUI.h("p", { class: "notice" }, data.display.notice) : null, FanboxUI.h("div", { class: "settings-grid two-columns" }, FanboxUI.h("div", { class: "setting-field" }, FanboxUI.h("span", {}, FanboxUI.t("settings.timezone")), select), otherField));
        return { node, read: () => choice === OTHER_TIMEZONE ? other.value.trim() : choice };
    }
    const THEMES = ["system", "dark", "light"];
    function applyTheme(theme) {
        document.documentElement.dataset.theme = theme === "system" ? "auto" : theme;
    }
    FanboxUI.applyTheme = applyTheme;
    function themeControl(data, blocked) {
        let choice = data.editable.display.theme;
        const select = FanboxUI.customSelect({ id: "display-theme", label: FanboxUI.t("settings.theme"), value: choice, disabled: blocked,
            options: THEMES.map(value => ({ value, label: FanboxUI.t(`settings.theme_${value}`) })),
            onChange: next => { choice = next; applyTheme(choice); } });
        const node = FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, FanboxUI.t("settings.theme")), FanboxUI.h("p", { class: "settings-section-description" }, FanboxUI.t("settings.theme_description")), FanboxUI.h("div", { class: "settings-grid two-columns" }, FanboxUI.h("div", { class: "setting-field" }, FanboxUI.h("span", {}, FanboxUI.t("settings.theme")), select)));
        return { node, read: () => choice };
    }
    const languageLabel = (value) => value === "auto" ? FanboxUI.t("settings.language_auto")
        : value === "qps-ploc" ? FanboxUI.t("settings.language_pseudo") : "繁體中文";
    function languageControl(data, blocked) {
        let choice = data.editable.display.language;
        const values = choice === "qps-ploc" ? ["auto", "zh-Hant", "qps-ploc"] : ["auto", "zh-Hant"];
        const select = FanboxUI.customSelect({ id: "display-language", label: FanboxUI.t("settings.language"), value: choice, disabled: blocked,
            options: values.map(value => ({ value, label: languageLabel(value) })),
            onChange: next => { choice = next; } });
        const node = FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, FanboxUI.t("settings.language")), FanboxUI.h("p", { class: "settings-section-description" }, FanboxUI.t("settings.language_description", { locale: FanboxUI.currentLocale() })), FanboxUI.h("div", { class: "settings-grid two-columns" }, FanboxUI.h("div", { class: "setting-field" }, FanboxUI.h("span", {}, FanboxUI.t("settings.language")), select)));
        return { node, read: () => choice };
    }
    async function copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        }
        catch {
            const area = FanboxUI.h("textarea", { readonly: true, class: "visually-hidden" });
            area.value = text;
            document.body.append(area);
            area.select();
            const copied = document.execCommand("copy");
            area.remove();
            return copied;
        }
    }
    function renderAboutSection(info, actions) {
        const card = FanboxUI.h("section", { class: "settings-card about-card" }, FanboxUI.h("p", { class: "eyebrow" }, "ABOUT & DIAGNOSTICS"), FanboxUI.h("h2", {}, FanboxUI.t("settings.tab_about")));
        if (!info) {
            card.append(FanboxUI.h("p", { class: "notice" }, FanboxUI.t("settings.about_unavailable")));
            return card;
        }
        const feedback = FanboxUI.h("p", { class: "about-feedback", role: "status", "aria-live": "polite" });
        const show = (text, error = false) => {
            feedback.textContent = text;
            feedback.classList.toggle("settings-error", error);
        };
        const supported = String(info.schema.supported);
        const schema = info.schema.database === null ? FanboxUI.t("settings.schema_unreadable", { supported })
            : FanboxUI.t("settings.schema_value", { database: String(info.schema.database), supported });
        const rows = [
            [FanboxUI.t("settings.about_app_version"), info.app_version],
            [FanboxUI.t("settings.about_mode"), info.mode === "desktop" ? FanboxUI.t("settings.about_desktop", { version: info.desktop_version ?? FanboxUI.t("settings.about_version_unknown") }) : FanboxUI.t("settings.about_browser")],
            [FanboxUI.t("settings.about_schema"), schema],
            ["Python", info.python_version],
            [FanboxUI.t("settings.about_os"), info.os],
            [FanboxUI.t("settings.timezone"), info.timezone],
            [FanboxUI.t("settings.about_config"), info.paths.config ?? FanboxUI.t("settings.about_unspecified")],
            [FanboxUI.t("settings.about_archive"), info.paths.archive],
            [FanboxUI.t("settings.about_database"), info.paths.database],
            [FanboxUI.t("settings.about_archive_logs"), info.paths.archive_logs],
        ];
        if (info.paths.desktop_logs)
            rows.push([FanboxUI.t("settings.about_desktop_logs"), info.paths.desktop_logs]);
        const folderButton = (target) => {
            const available = info.can_open_folders && info.folders[target];
            return FanboxUI.h("button", { type: "button", disabled: !available,
                title: !info.can_open_folders ? FanboxUI.t("settings.folder_unsupported") : info.folders[target] ? ""
                    : FanboxUI.t(`settings.folder_missing_${target}`),
                onclick: async (event) => {
                    const button = event.currentTarget;
                    button.disabled = true;
                    const error = await actions.onOpen(target);
                    button.disabled = false;
                    show(error ? FanboxUI.t("settings.folder_open_failed", { error })
                        : FanboxUI.t("settings.folder_opened", { name: FanboxUI.t(`settings.folder_${target}`) }), Boolean(error));
                } }, FanboxUI.t(`settings.open_${target}`));
        };
        card.append(FanboxUI.h("p", { class: "settings-section-description" }, FanboxUI.t("settings.about_description")), ...(info.notices ?? []).map(text => FanboxUI.h("p", { class: "notice" }, text)), FanboxUI.h("div", { class: "settings-paths about-facts" }, rows.map(([label, value]) => FanboxUI.h("div", {}, FanboxUI.h("span", {}, label), FanboxUI.h("code", {}, value)))), FanboxUI.h("div", { class: "account-actions about-actions" }, folderButton("archive"), folderButton("archive_logs"), info.paths.desktop_logs ? folderButton("desktop_logs") : null, FanboxUI.h("button", { type: "button", onclick: async () => {
                show(await copyText(info.text) ? FanboxUI.t("settings.copied") : FanboxUI.t("settings.copy_failed"), false);
            } }, FanboxUI.t("settings.copy_diagnostics"))), feedback);
        return card;
    }
    FanboxUI.SETTINGS_TABS = ["account", "general", "backup", "theme", "about"];
    function isSettingsTab(value) {
        return FanboxUI.SETTINGS_TABS.includes(value);
    }
    FanboxUI.isSettingsTab = isSettingsTab;
    const authLabel = (state) => FanboxUI.t(`settings.auth_${state}`);
    function renderAccountCard(auth, blocked, actions) {
        if (!auth) {
            return FanboxUI.h("section", { class: "settings-card account-card tone-neutral", "aria-busy": "true" }, FanboxUI.h("div", { class: "account-heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "ACCOUNT & SIGN-IN"), FanboxUI.h("h2", {}, FanboxUI.t("settings.account_title"))), FanboxUI.h("span", { class: "auth-badge neutral" }, authLabel("checking"))), FanboxUI.h("p", { class: "account-message", role: "status", "aria-live": "polite" }, FanboxUI.t("settings.account_checking")));
        }
        const authBusy = auth.state === "checking";
        const authLocked = auth.state === "locked";
        const authTone = auth.state === "authenticated" ? "success"
            : auth.state === "expired" || auth.state === "error" ? "error" : "neutral";
        const lastKnown = authLocked && auth.last_known
            ? FanboxUI.t("settings.last_known", { state: authLabel(auth.last_known.state), time: FanboxUI.formatDate(auth.last_known.checked_at) })
            : null;
        const authFeedback = FanboxUI.h("p", { class: "settings-error", role: "alert", hidden: true });
        const runAuth = async (action) => {
            authFeedback.hidden = true;
            const error = await action();
            if (error) {
                authFeedback.textContent = error;
                authFeedback.hidden = false;
            }
        };
        return FanboxUI.h("section", { class: `settings-card account-card tone-${authTone}` }, FanboxUI.h("div", { class: "account-heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "ACCOUNT & SIGN-IN"), FanboxUI.h("h2", {}, FanboxUI.t("settings.account_title"))), FanboxUI.h("span", { class: `auth-badge ${authTone}` }, authLabel(auth.state))), FanboxUI.h("p", { class: "account-message", role: "status", "aria-live": "polite" }, auth.message), lastKnown ? FanboxUI.h("p", { class: "account-last-known" }, lastKnown) : null, FanboxUI.h("p", { class: "settings-section-description" }, auth.source === "profile"
            ? FanboxUI.t("settings.source_profile")
            : auth.source === "environment" ? FanboxUI.t("settings.source_environment")
                : FanboxUI.t("settings.source_none")), auth.externally_managed ? FanboxUI.h("p", { class: "auth-external-notice" }, FanboxUI.t("settings.external_notice")) : null, FanboxUI.h("div", { class: "account-actions" }, FanboxUI.h("button", { type: "button", class: "primary", disabled: blocked || authLocked || authBusy || !auth.can_login,
            onclick: () => void runAuth(actions.onLogin) }, FanboxUI.t("settings.login")), FanboxUI.h("button", { type: "button", disabled: blocked || authLocked || authBusy, onclick: actions.onRefresh }, FanboxUI.t("settings.recheck")), authBusy && auth.job ? FanboxUI.h("button", { type: "button", class: "danger-outline",
            onclick: () => void runAuth(() => actions.onCancel(auth.job.job_id)) }, FanboxUI.t("settings.cancel_login")) : null, FanboxUI.h("button", { type: "button", class: "danger-outline",
            disabled: blocked || authLocked || authBusy || !auth.can_logout,
            onclick: async () => {
                const confirmed = await FanboxUI.confirmDialog({
                    title: FanboxUI.t("settings.logout_title"), message: FanboxUI.t("settings.logout_message"),
                    cancelLabel: FanboxUI.t("settings.logout_cancel"), confirmLabel: FanboxUI.t("settings.logout"), danger: true,
                });
                if (confirmed)
                    void runAuth(actions.onLogout);
            } }, FanboxUI.t("settings.logout")), authFeedback));
    }
    function generalPage(data, blocked) {
        const value = data.editable;
        const language = languageControl(data, blocked);
        const timezone = timezoneControl(data, blocked);
        const markdown = settingCheckbox(FanboxUI.t("settings.markdown_enabled"), value.markdown.enabled);
        const frontMatter = settingCheckbox(FanboxUI.t("settings.markdown_front_matter"), value.markdown.yaml_front_matter);
        const relativePaths = settingCheckbox(FanboxUI.t("settings.markdown_relative_paths"), value.markdown.relative_image_paths);
        const preserveOrder = settingCheckbox(FanboxUI.t("settings.markdown_original_order"), value.markdown.preserve_original_order);
        const logLevel = FanboxUI.customSelect({ id: "log-level", label: FanboxUI.t("settings.log_level"), value: value.logging.level, disabled: blocked,
            options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map(item => ({ value: item, label: item })) });
        const logLevelField = FanboxUI.h("div", { class: "setting-field" }, FanboxUI.h("span", {}, FanboxUI.t("settings.log_level")), logLevel);
        const keepDays = settingNumber(FanboxUI.t("settings.log_keep_days"), value.logging.keep_days, 1, 365);
        const fileLogs = settingCheckbox(FanboxUI.t("settings.log_to_file"), value.logging.write_to_file);
        const checked = (control) => ({ node: control.node, read: () => control.input.checked });
        return {
            content: [FanboxUI.h("section", { class: "settings-card" }, FanboxUI.h("p", { class: "eyebrow" }, "GENERAL"), FanboxUI.h("h2", {}, FanboxUI.t("settings.tab_general")), language.node, timezone.node, FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, "Markdown"), FanboxUI.h("div", { class: "setting-toggles" }, markdown.node, frontMatter.node, relativePaths.node, preserveOrder.node)), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, FanboxUI.t("settings.logs")), FanboxUI.h("div", { class: "settings-grid two-columns" }, logLevelField, keepDays.node), FanboxUI.h("div", { class: "setting-toggles" }, fileLogs.node)))],
            fields: [
                { node: language.node, read: language.read }, { node: timezone.node, read: timezone.read },
                checked(markdown), checked(frontMatter), checked(relativePaths), checked(preserveOrder),
                { node: logLevelField, read: () => logLevel.value }, { node: keepDays.node, read: () => keepDays.input.value },
                checked(fileLogs),
            ],
            patch: () => ({
                display: { timezone: timezone.read(), language: language.read() },
                markdown: { enabled: markdown.input.checked, yaml_front_matter: frontMatter.input.checked,
                    relative_image_paths: relativePaths.input.checked, preserve_original_order: preserveOrder.input.checked },
                logging: { level: logLevel.value, write_to_file: fileLogs.input.checked, keep_days: Number(keepDays.input.value) },
            }),
        };
    }
    function themePage(data, blocked) {
        const theme = themeControl(data, blocked);
        const colors = FanboxUI.colorEditor(data);
        return {
            content: [FanboxUI.h("section", { class: "settings-card" }, FanboxUI.h("p", { class: "eyebrow" }, "THEME"), FanboxUI.h("h2", {}, FanboxUI.t("settings.tab_theme")), theme.node, colors.node)],
            fields: [{ node: theme.node, read: theme.read }, { node: colors.node, read: colors.read }],
            patch: () => ({ display: { theme: theme.read(), colors: colors.read() } }),
        };
    }
    function backupPage(data, blocked, schedule) {
        const value = data.editable;
        const maxPosts = settingNumber(FanboxUI.t("settings.max_posts"), value.sync.max_posts_per_run, 1, 100, 1, FanboxUI.t("settings.max_posts_hint"));
        const unchangedStop = settingNumber(FanboxUI.t("settings.unchanged_stop"), value.sync.recent_unchanged_stop_count, 1, 500, 1, FanboxUI.t("settings.unchanged_stop_hint"));
        const defaultDryRun = settingCheckbox(FanboxUI.t("settings.default_dry_run"), value.backup_defaults.dry_run);
        const defaultProfile = settingCheckbox(FanboxUI.t("settings.default_profile"), value.backup_defaults.include_profile);
        const defaultFancard = settingCheckbox(FanboxUI.t("settings.default_fancard"), value.backup_defaults.include_fancard);
        const originalImages = settingCheckbox(FanboxUI.t("settings.original_images"), value.download.original_images);
        const attachments = settingCheckbox(FanboxUI.t("settings.attachments"), value.download.download_attachments);
        const covers = settingCheckbox(FanboxUI.t("settings.covers"), value.download.download_cover);
        const resume = settingCheckbox(FanboxUI.t("settings.resume"), value.download.resume);
        const hashes = settingCheckbox(FanboxUI.t("settings.verify_sha256"), value.download.verify_sha256);
        const preserveDeleted = settingCheckbox(FanboxUI.t("settings.preserve_deleted"), value.sync.preserve_deleted_posts);
        const skipCompleted = settingCheckbox(FanboxUI.t("settings.skip_completed"), value.sync.skip_completed);
        const checkUpdates = settingCheckbox(FanboxUI.t("settings.check_updates"), value.sync.check_updates);
        const rotate = settingCheckbox(FanboxUI.t("settings.rotate_creators"), value.sync.rotate_creators);
        const retries = settingNumber(FanboxUI.t("settings.retries"), value.download.retry_count, 0, 10);
        const interval = settingNumber(FanboxUI.t("settings.request_interval"), value.download.request_interval_seconds, 1, 3600, .5, FanboxUI.t("settings.request_interval_hint"));
        const timeout = settingNumber(FanboxUI.t("settings.request_timeout"), value.download.timeout_seconds, 5, 600);
        const scheduleSection = FanboxUI.renderScheduleSection(value.schedule, schedule.status, schedule.creators, blocked, schedule.actions);
        const checked = (control) => ({ node: control.node, read: () => control.input.checked });
        const number = (control) => ({ node: control.node, read: () => control.input.value });
        return {
            content: [FanboxUI.h("section", { class: "settings-card backup-settings" }, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP"), FanboxUI.h("h2", {}, FanboxUI.t("settings.tab_backup")), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, FanboxUI.t("settings.section_quota")), FanboxUI.h("p", { class: "settings-section-description" }, FanboxUI.t("settings.section_quota_description")), FanboxUI.h("div", { class: "settings-grid two-columns" }, maxPosts.node, unchangedStop.node)), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, FanboxUI.t("settings.section_defaults")), FanboxUI.h("p", { class: "settings-section-description" }, FanboxUI.t("settings.section_defaults_description")), FanboxUI.h("div", { class: "setting-toggles" }, defaultDryRun.node, defaultProfile.node, defaultFancard.node)), scheduleSection.node, FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, FanboxUI.t("settings.section_content")), FanboxUI.h("div", { class: "setting-toggles" }, originalImages.node, attachments.node, covers.node, resume.node, hashes.node, preserveDeleted.node)), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, FanboxUI.t("settings.section_updates")), FanboxUI.h("div", { class: "setting-toggles" }, skipCompleted.node, checkUpdates.node, rotate.node)), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, FanboxUI.t("settings.section_network")), FanboxUI.h("div", { class: "settings-grid" }, retries.node, interval.node, timeout.node)))],
            fields: [
                number(maxPosts), number(unchangedStop), checked(defaultDryRun), checked(defaultProfile), checked(defaultFancard),
                ...scheduleSection.fields,
                checked(originalImages), checked(attachments), checked(covers), checked(resume), checked(hashes),
                checked(preserveDeleted), checked(skipCompleted), checked(checkUpdates), checked(rotate),
                number(retries), number(interval), number(timeout),
            ],
            patch: () => ({
                download: {
                    original_images: originalImages.input.checked, download_attachments: attachments.input.checked,
                    download_cover: covers.input.checked, resume: resume.input.checked, verify_sha256: hashes.input.checked,
                    retry_count: Number(retries.input.value), request_interval_seconds: Number(interval.input.value),
                    timeout_seconds: Number(timeout.input.value),
                },
                sync: {
                    skip_completed: skipCompleted.input.checked, check_updates: checkUpdates.input.checked,
                    preserve_deleted_posts: preserveDeleted.input.checked, rotate_creators: rotate.input.checked,
                    max_posts_per_run: Number(maxPosts.input.value),
                    recent_unchanged_stop_count: Number(unchangedStop.input.value),
                },
                backup_defaults: {
                    dry_run: defaultDryRun.input.checked, include_profile: defaultProfile.input.checked,
                    include_fancard: defaultFancard.input.checked,
                },
                schedule: scheduleSection.read(),
            }),
            onDirty: dirty => scheduleSection.setRunBlocked(dirty ? FanboxUI.t("settings.run_blocked_unsaved") : null),
            onLocked: locked => scheduleSection.setLocked(locked),
        };
    }
    function renderSettingsPage(ctx) {
        const { data, tab } = ctx;
        let blocked = Boolean(ctx.activeJob);
        const tabButtons = new Map();
        const tabs = FanboxUI.h("nav", { class: "settings-tabs", "aria-label": FanboxUI.t("settings.tabs_label") }, FanboxUI.SETTINGS_TABS.map(item => {
            const button = FanboxUI.h("button", { type: "button", "data-settings-tab": item,
                "aria-current": item === tab ? "page" : null, class: item === tab ? "active" : "",
                onclick: () => { if (item !== tab)
                    ctx.onTab(item); } }, FanboxUI.h("span", {}, FanboxUI.t(`settings.tab_${item}`)));
            tabButtons.set(item, button);
            return button;
        }));
        const markTab = (dirty) => {
            const button = tabButtons.get(tab);
            if (!button)
                return;
            button.querySelector(".tab-dirty")?.remove();
            if (dirty)
                button.append(FanboxUI.h("span", { class: "tab-dirty" }, FanboxUI.t("settings.tab_unsaved")));
        };
        let notice = FanboxUI.activeJobNotice(ctx.activeJob) ?? FanboxUI.h("div", { hidden: true });
        const body = FanboxUI.h("div", { class: "settings-body" });
        let tracker = null;
        let fieldset = null;
        let save = null;
        let lockNote = null;
        let account = null;
        let auth = ctx.auth ?? null;
        const editable = tab === "general" ? generalPage(data, blocked)
            : tab === "theme" ? themePage(data, blocked)
                : tab === "backup" && ctx.schedule ? backupPage(data, blocked, ctx.schedule) : null;
        if (editable) {
            const feedback = FanboxUI.h("p", { class: "settings-error", role: "alert", hidden: true });
            save = FanboxUI.h("button", { type: "submit", class: "primary", disabled: !data.writable || blocked }, FanboxUI.t("settings.save"));
            lockNote = FanboxUI.h("span", { class: "notice", hidden: !blocked }, FanboxUI.t("settings.locked_note"));
            fieldset = FanboxUI.h("fieldset", { disabled: blocked }, ...editable.content);
            const form = FanboxUI.h("form", { class: "settings-form", "aria-disabled": blocked, onsubmit: async (event) => {
                    event.preventDefault();
                    if (blocked)
                        return;
                    feedback.hidden = true;
                    save.disabled = true;
                    const error = await ctx.onSave(editable.patch());
                    if (save.isConnected)
                        save.disabled = !data.writable || blocked;
                    if (error) {
                        feedback.textContent = FanboxUI.t("settings.save_failed", { error });
                        feedback.hidden = false;
                    }
                } }, fieldset, FanboxUI.h("div", { class: "settings-actions" }, save, !data.writable ? FanboxUI.h("span", { class: "notice" }, FanboxUI.t("settings.not_writable")) : null, lockNote, feedback));
            body.append(form);
            tracker = FanboxUI.trackChanges(form, editable.fields, dirty => { markTab(dirty); editable.onDirty?.(dirty); });
        }
        else if (tab === "account" && ctx.account) {
            account = renderAccountCard(auth, blocked, ctx.account);
            body.append(account);
        }
        else if (tab === "about" && ctx.about) {
            body.append(renderAboutSection(ctx.about.info, ctx.about.actions));
        }
        const node = FanboxUI.h("section", { class: "page settings-page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "LOCAL SETTINGS"), FanboxUI.h("h1", {}, FanboxUI.t("settings.title")), FanboxUI.h("p", {}, FanboxUI.t("settings.subtitle")))), tabs, ctx.message ? FanboxUI.h("p", { class: "settings-saved", role: "status" }, ctx.message) : null, notice, body);
        requestAnimationFrame(() => tabButtons.get(tab)?.scrollIntoView({ block: "nearest", inline: "nearest" }));
        return {
            node,
            isDirty: () => tracker?.isDirty() ?? false,
            setLocked: activeJob => {
                const next = Boolean(activeJob);
                const replacement = FanboxUI.activeJobNotice(activeJob) ?? FanboxUI.h("div", { hidden: true });
                notice.replaceWith(replacement);
                notice = replacement;
                if (next === blocked)
                    return;
                blocked = next;
                if (fieldset) {
                    fieldset.disabled = blocked;
                    for (const select of fieldset.querySelectorAll(".custom-select"))
                        select.disabled = blocked;
                }
                editable?.onLocked?.(blocked);
                if (save)
                    save.disabled = !data.writable || blocked;
                if (lockNote)
                    lockNote.hidden = !blocked;
                if (account && ctx.account) {
                    const card = renderAccountCard(auth, blocked, ctx.account);
                    account.replaceWith(card);
                    account = card;
                }
            },
            setAuth: next => {
                auth = next;
                if (!account || !ctx.account)
                    return;
                const card = renderAccountCard(auth, blocked, ctx.account);
                account.replaceWith(card);
                account = card;
            },
        };
    }
    FanboxUI.renderSettingsPage = renderSettingsPage;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    const activeStatuses = new Set(["queued", "running", "cancelling"]);
    function jobLabel(job) {
        if (job.kind === "verify")
            return FanboxUI.t("jobs.kind_verify");
        if (job.request.trigger === "schedule")
            return FanboxUI.t("jobs.kind_schedule");
        return { profile: FanboxUI.t("jobs.kind_profile"), fancard: FanboxUI.t("jobs.kind_fancard") }[job.request.mode ?? ""]
            || (job.request.dry_run ? FanboxUI.t("jobs.kind_preview") : FanboxUI.t("jobs.kind_full"));
    }
    FanboxUI.jobLabel = jobLabel;
    function activeJobNotice(job) {
        if (!job)
            return null;
        return FanboxUI.h("p", { class: "global-job-notice", role: "status" }, FanboxUI.h("strong", {}, FanboxUI.t("jobs.current_job", { label: jobLabel(job) })), FanboxUI.t("jobs.current_state", { state: job.external ? FanboxUI.t("jobs.running_in_background") : statusText(job.status) }), FanboxUI.h("span", {}, job.external ? FanboxUI.t("jobs.background_notice") : FanboxUI.t("jobs.single_job_notice")));
    }
    FanboxUI.activeJobNotice = activeJobNotice;
    function valueNumber(data, key) {
        const value = Number(data[key] ?? 0);
        return Number.isFinite(value) ? value : 0;
    }
    function valueString(data, key) {
        const value = data[key];
        return value === null || value === undefined ? "" : String(value);
    }
    function isRecord(value) {
        return Boolean(value) && typeof value === "object" && !Array.isArray(value);
    }
    function stopReasonLabel(reason) {
        const known = ["limit_reached", "remote_exhausted", "backfill_completed", "unchanged_threshold", "eligible_exhausted"];
        return known.includes(reason) ? FanboxUI.t(`jobs.stop_${reason}`) : FanboxUI.t("jobs.stop_default");
    }
    FanboxUI.stopReasonLabel = stopReasonLabel;
    function isActiveJob(job) {
        return Boolean(job && activeStatuses.has(job.status));
    }
    FanboxUI.isActiveJob = isActiveJob;
    function requestCreators(request) {
        if (Array.isArray(request.creators))
            return [...new Set(request.creators.filter(Boolean))];
        return request.creator ? [request.creator] : [];
    }
    FanboxUI.requestCreators = requestCreators;
    function filterBackupCreators(creators, query, selected) {
        const term = query.trim().toLocaleLowerCase();
        const chosen = new Set(selected);
        return creators.filter(item => !chosen.has(item.creator_id)
            && (!term || `${item.name} ${item.creator_id}`.toLocaleLowerCase().includes(term)));
    }
    FanboxUI.filterBackupCreators = filterBackupCreators;
    function jobCreatorLabel(job, creators) {
        const selected = requestCreators(job.request);
        if (!selected.length)
            return FanboxUI.t("jobs.all_creators");
        if (selected.length > 1)
            return FanboxUI.t("jobs.creator_count", { count: selected.length });
        const item = creators.find(creator => creator.creator_id === selected[0]);
        return item ? FanboxUI.t("jobs.creator_named", { name: item.name, creator_id: item.creator_id }) : `@${selected[0]}`;
    }
    FanboxUI.jobCreatorLabel = jobCreatorLabel;
    function statusText(status) {
        return FanboxUI.t(`jobs.status_${status}`);
    }
    FanboxUI.statusText = statusText;
    function eventLabel(event) {
        const data = event.data;
        if (event.kind === "job_started")
            return FanboxUI.t("jobs.event_started", { scope: valueString(data, "scope") });
        if (event.kind === "plan_ready")
            return FanboxUI.t("jobs.event_plan", {
                requested: valueNumber(data, "requested_max_posts"), discovered: valueNumber(data, "discovered"),
                eligible: valueNumber(data, "eligible"), selected: valueNumber(data, "selected"),
                skipped: valueNumber(data, "skipped"), reason: stopReasonLabel(valueString(data, "stop_reason"))
            });
        if (event.kind === "fancard_finished")
            return FanboxUI.t("jobs.event_fancard", {
                creator_id: valueString(data, "creator_id"), status: valueString(data, "status")
            });
        if (event.kind === "profile_started")
            return FanboxUI.t("jobs.event_profile_started", { creator_id: valueString(data, "creator_id") });
        if (event.kind === "profile_finished")
            return FanboxUI.t("jobs.event_profile_finished", {
                creator_id: valueString(data, "creator_id"), status: valueString(data, "status"),
                version: String(valueNumber(data, "version")).padStart(4, "0")
            });
        if (event.kind === "profile_warning")
            return FanboxUI.t("jobs.event_profile_warning", {
                creator_id: valueString(data, "creator_id"), message: valueString(data, "message")
            });
        if (event.kind === "asset_progress") {
            const total = valueNumber(data, "total");
            return FanboxUI.t("jobs.event_asset", { name: valueString(data, "name"),
                progress: `${FanboxUI.humanBytes(valueNumber(data, "downloaded"))}${total ? ` / ${FanboxUI.humanBytes(total)}` : ""}` });
        }
        if (event.kind === "item_started")
            return FanboxUI.t("jobs.event_item_started", {
                index: valueNumber(data, "index"), total: valueNumber(data, "total"), post_id: valueString(data, "post_id")
            });
        if (event.kind === "item_finished")
            return FanboxUI.t("jobs.event_item_finished", { post_id: valueString(data, "post_id"),
                result: data.unchanged ? FanboxUI.t("jobs.event_unchanged") : valueString(data, "error") || valueString(data, "status") });
        if (event.kind === "verify_progress")
            return FanboxUI.t("jobs.event_verify", {
                phase: verificationPhaseLabel(valueString(data, "phase")), item: valueString(data, "item")
            });
        if (event.kind === "warning")
            return data.creator_id
                ? FanboxUI.t("jobs.event_warning_creator", { creator_id: valueString(data, "creator_id"), message: valueString(data, "message") })
                : FanboxUI.t("jobs.event_warning", { message: valueString(data, "message") });
        if (event.kind === "job_finished")
            return data.dry_run ? FanboxUI.t("jobs.event_preview_done")
                : FanboxUI.t("jobs.event_done", { success: valueNumber(data, "success"), failure: valueNumber(data, "failure") });
        if (event.kind === "job_failed")
            return FanboxUI.t("jobs.event_failed", { error: valueString(data, "error") });
        if (event.kind === "job_cancelled")
            return FanboxUI.t("jobs.event_cancelled");
        if (event.kind === "job_interrupted")
            return FanboxUI.t("jobs.event_interrupted");
        return event.kind;
    }
    function eventTone(kind) {
        if (["warning", "profile_warning", "job_interrupted"].includes(kind))
            return "warning";
        if (kind === "job_failed")
            return "error";
        if (kind === "plan_ready")
            return "plan";
        if (kind === "job_finished")
            return "success";
        return "neutral";
    }
    function planSummary(event, creators) {
        if (!event)
            return null;
        const data = event.data;
        const creatorNames = new Map(creators.map(item => [item.creator_id, item.name]));
        const metrics = [[FanboxUI.t("jobs.metric_new"), valueNumber(data, "new"), "new"],
            [FanboxUI.t("jobs.metric_updated"), valueNumber(data, "updated"), "updated"], [FanboxUI.t("jobs.metric_retry"), valueNumber(data, "retried"), "retry"],
            [FanboxUI.t("jobs.metric_skipped"), valueNumber(data, "skipped"), "skipped"]];
        const scans = Array.isArray(data.scans) ? data.scans.filter(isRecord) : [];
        const rows = scans.map(scan => {
            const creatorId = valueString(scan, "creator_id");
            const profile = valueString(scan, "profile");
            return FanboxUI.h("tr", {}, FanboxUI.h("th", { scope: "row" }, FanboxUI.h("strong", {}, creatorNames.get(creatorId) || creatorId), FanboxUI.h("small", {}, creatorId)), FanboxUI.h("td", { class: "number new" }, valueNumber(scan, "new")), FanboxUI.h("td", { class: "number updated" }, valueNumber(scan, "updated")), FanboxUI.h("td", { class: "number retry" }, valueNumber(scan, "retry")), FanboxUI.h("td", { class: "number skipped" }, valueNumber(scan, "skipped")), FanboxUI.h("td", { class: "number" }, valueNumber(scan, "discovered")), FanboxUI.h("td", { class: `profile-result ${profile || "none"}` }, profile || "—"));
        });
        const creatorCount = Array.isArray(data.creators) ? data.creators.length : valueNumber(data, "creators") || rows.length;
        const requested = valueNumber(data, "requested_max_posts");
        const selected = valueNumber(data, "selected");
        const reason = stopReasonLabel(valueString(data, "stop_reason"));
        return FanboxUI.h("section", { class: "plan-panel" }, FanboxUI.h("div", { class: "section-title" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP PLAN"), FanboxUI.h("h2", {}, FanboxUI.t("jobs.plan_title"))), FanboxUI.h("span", { class: "plan-creators" }, FanboxUI.t("jobs.creator_count", { count: creatorCount }))), FanboxUI.h("p", { class: "plan-capacity" }, FanboxUI.t("jobs.plan_capacity", { requested, discovered: valueNumber(data, "discovered"),
            eligible: valueNumber(data, "eligible"), selected, skipped: valueNumber(data, "skipped") }), selected < requested ? FanboxUI.h("strong", {}, reason) : null), FanboxUI.h("div", { class: "metric-grid" }, metrics.map(([label, value, tone]) => FanboxUI.h("div", { class: `metric ${tone}` }, FanboxUI.h("strong", {}, value), FanboxUI.h("span", {}, label)))), rows.length ? FanboxUI.h("div", { class: "table-scroll" }, FanboxUI.h("table", { class: "plan-table" }, FanboxUI.h("thead", {}, FanboxUI.h("tr", {}, FanboxUI.h("th", {}, FanboxUI.t("jobs.column_creator")), FanboxUI.h("th", {}, FanboxUI.t("jobs.metric_new")), FanboxUI.h("th", {}, FanboxUI.t("jobs.metric_updated")), FanboxUI.h("th", {}, FanboxUI.t("jobs.metric_retry")), FanboxUI.h("th", {}, FanboxUI.t("jobs.metric_skipped")), FanboxUI.h("th", {}, FanboxUI.t("jobs.metric_discovered")), FanboxUI.h("th", {}, "Profile"))), FanboxUI.h("tbody", {}, rows))) : null);
    }
    function currentActivity(job) {
        const events = job.events ?? [];
        const event = [...events].reverse().find(item => ["asset_progress", "item_started", "item_finished", "fancard_finished",
            "profile_started", "profile_finished", "profile_warning", "warning", "job_failed", "job_finished",
            "job_cancelled", "job_interrupted", "job_started"].includes(item.kind));
        if (!event)
            return FanboxUI.h("section", { class: "current-activity" }, FanboxUI.h("p", { class: "eyebrow" }, "CURRENT"), FanboxUI.h("h2", {}, FanboxUI.t("jobs.preparing")));
        const postEvent = [...events].reverse().find(item => ["item_started", "item_finished", "asset_progress"].includes(item.kind)
            && valueNumber(item.data, "index") > 0 && valueNumber(item.data, "total") > 0);
        const isAsset = event.kind === "asset_progress";
        const total = valueNumber(event.data, "total");
        const downloaded = valueNumber(event.data, "downloaded");
        const percent = total > 0 ? Math.min(100, Math.max(0, downloaded / total * 100)) : null;
        return FanboxUI.h("section", { class: `current-activity tone-${eventTone(event.kind)}` }, FanboxUI.h("div", { class: "activity-top" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, isAsset ? "CURRENT DOWNLOAD" : "CURRENT STATUS"), FanboxUI.h("h2", {}, isAsset ? valueString(event.data, "name") || FanboxUI.t("jobs.download_asset") : eventLabel(event))), FanboxUI.h("time", {}, FanboxUI.formatDate(event.timestamp))), postEvent ? FanboxUI.h("div", { class: "progress-area post-progress", role: "status", "aria-live": "polite", "aria-atomic": "true" }, FanboxUI.h("div", { class: "progress-label" }, FanboxUI.h("span", {}, FanboxUI.t("jobs.post_progress", { index: valueNumber(postEvent.data, "index"), total: valueNumber(postEvent.data, "total") })), FanboxUI.h("strong", {}, `Post ${valueString(postEvent.data, "post_id")}`)), FanboxUI.h("progress", { max: valueNumber(postEvent.data, "total"),
            value: Math.min(valueNumber(postEvent.data, "index"), valueNumber(postEvent.data, "total")),
            "aria-label": FanboxUI.t("jobs.post_progress_label") })) : null, isAsset ? FanboxUI.h("div", { class: "progress-area" }, FanboxUI.h("div", { class: "progress-label" }, FanboxUI.h("span", {}, `${FanboxUI.humanBytes(downloaded)}${total ? ` / ${FanboxUI.humanBytes(total)}` : ""}`), FanboxUI.h("strong", {}, percent === null ? FanboxUI.t("jobs.downloading") : `${percent.toFixed(1)}%`)), FanboxUI.h("progress", { max: total || 1, value: downloaded, "aria-label": FanboxUI.t("jobs.asset_progress_label") })) : null);
    }
    function verificationPhaseLabel(phase) {
        const known = ["scan", "posts", "versions", "fancards", "profiles", "consistency", "history"];
        return known.includes(phase) ? FanboxUI.t(`jobs.phase_${phase}`) : FanboxUI.t("jobs.phase_default");
    }
    FanboxUI.verificationPhaseLabel = verificationPhaseLabel;
    function verificationProgress(job) {
        const event = [...(job?.events ?? [])].reverse().find(item => item.kind === "verify_progress");
        if (!event || job?.result)
            return null;
        const totalValue = event.data.total;
        const total = totalValue === null || totalValue === undefined ? null : valueNumber(event.data, "total");
        const current = valueNumber(event.data, "current");
        const percent = total === null ? null : Math.min(100, Math.max(0, valueNumber(event.data, "percent")));
        return FanboxUI.h("section", { class: "verification-progress", role: "status", "aria-live": "polite", "aria-atomic": "true" }, FanboxUI.h("div", { class: "verification-progress-heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "VERIFY PROGRESS"), FanboxUI.h("h2", {}, verificationPhaseLabel(valueString(event.data, "phase")))), FanboxUI.h("strong", {}, percent === null ? FanboxUI.t("jobs.scanning") : `${percent.toFixed(1)}%`)), FanboxUI.h("p", { class: "verification-item" }, valueString(event.data, "item")), FanboxUI.h("div", { class: "progress-label" }, FanboxUI.h("span", {}, total === null ? FanboxUI.t("jobs.building_checklist") : `${current} / ${total}`), FanboxUI.h("span", {}, FanboxUI.t("jobs.issues_found", { count: valueNumber(event.data, "issue_count") }))), FanboxUI.h("progress", { max: total ?? undefined, value: total === null ? undefined : current,
            "aria-label": total === null ? FanboxUI.t("jobs.verify_scan_label") : FanboxUI.t("jobs.verify_progress_label") }));
    }
    function eventLog(events) {
        const rows = events.map(item => FanboxUI.h("li", { class: `event-${eventTone(item.kind)}` }, FanboxUI.h("span", { class: "event-mark", "aria-hidden": "true" }), FanboxUI.h("time", {}, FanboxUI.formatDate(item.timestamp)), FanboxUI.h("span", { class: "event-kind" }, item.kind === "plan_ready" ? FanboxUI.t("jobs.log_plan")
            : ["warning", "profile_warning", "job_interrupted"].includes(item.kind) ? FanboxUI.t("jobs.log_warning")
                : item.kind === "job_failed" ? FanboxUI.t("jobs.log_error") : FanboxUI.t("jobs.log_record")), FanboxUI.h("span", { class: "event-message" }, eventLabel(item))));
        const details = FanboxUI.h("details", { class: "job-details" }, FanboxUI.h("summary", {}, FanboxUI.h("span", {}, FanboxUI.t("jobs.log_title")), FanboxUI.h("small", {}, FanboxUI.t("jobs.log_count", { count: events.length }))), FanboxUI.h("ol", { class: "event-log" }, rows.length ? rows : FanboxUI.h("li", { class: "event-neutral" }, FanboxUI.t("jobs.log_waiting"))));
        details.addEventListener("toggle", () => {
            if (!details.open)
                return;
            const log = details.querySelector(".event-log");
            if (log)
                log.scrollTop = log.scrollHeight;
        });
        return details;
    }
    function jobPart(node, name) {
        node.dataset.jobPart = name;
        return node;
    }
    function updateJobPage(current, next, preserveHistory = false) {
        const currentParts = new Map([...current.children].map(node => [node.dataset.jobPart, node]));
        for (const item of [...next.children]) {
            const nextPart = item;
            const name = nextPart.dataset.jobPart;
            const currentPart = currentParts.get(name);
            if (!currentPart) {
                current.append(nextPart);
                continue;
            }
            if (name === "history" && preserveHistory) {
                currentParts.delete(name);
                continue;
            }
            if (name === "details") {
                const details = currentPart;
                const wasOpen = details.open;
                const log = details.querySelector(".event-log");
                const previousScrollTop = log?.scrollTop ?? 0;
                const nearBottom = log ? log.scrollHeight - log.scrollTop - log.clientHeight < 40 : true;
                currentPart.replaceChildren(...nextPart.childNodes);
                details.open = wasOpen;
                const updatedLog = details.querySelector(".event-log");
                if (wasOpen && updatedLog)
                    updatedLog.scrollTop = nearBottom ? updatedLog.scrollHeight : previousScrollTop;
            }
            else
                currentPart.replaceWith(nextPart);
            currentParts.delete(name);
        }
        for (const stale of currentParts.values())
            stale.remove();
    }
    FanboxUI.updateJobPage = updateJobPage;
    function jobModeLabel(job) {
        if (job.request.trigger === "schedule")
            return FanboxUI.t("jobs.kind_schedule");
        return { profile: FanboxUI.t("jobs.mode_profile"), fancard: FanboxUI.t("jobs.mode_fancard") }[job.request.mode ?? ""]
            || (job.request.dry_run ? FanboxUI.t("jobs.kind_preview") : FanboxUI.t("jobs.kind_full"));
    }
    function jobHistory(data, selectedId, creators, filterValue, order, actions) {
        const active = data.active;
        const filter = FanboxUI.customSelect({ id: "job-history-filter", label: FanboxUI.t("jobs.filter_label"), value: filterValue, options: [
                { value: "all", label: FanboxUI.t("jobs.filter_all") },
                ...["completed", "failed", "interrupted", "cancelled"].map(value => ({ value, label: statusText(value) })),
            ], onChange: actions.onFilter });
        const rows = data.items.map(item => FanboxUI.h("button", { type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
            disabled: Boolean(active && item.job_id !== active.job_id), onclick: () => actions.onShow(item.job_id) }, FanboxUI.h("span", { class: `history-status status-${item.status}` }, statusText(item.status)), FanboxUI.h("span", { class: "history-main" }, FanboxUI.h("strong", {}, jobModeLabel(item)), FanboxUI.h("small", {}, `${jobCreatorLabel(item, creators)} · ${FanboxUI.formatDate(item.created_at)}`)), FanboxUI.h("span", { class: "history-result" }, item.result
            ? FanboxUI.t("jobs.history_result", { success: item.result.success ?? 0, failure: item.result.failure ?? 0 })
            : item.error ? FanboxUI.t("jobs.view_error") : FanboxUI.t("jobs.view_details"))));
        return FanboxUI.h("section", { class: "job-history" }, FanboxUI.h("div", { class: "history-heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "JOB HISTORY"), FanboxUI.h("h2", {}, FanboxUI.t("jobs.history_title"))), FanboxUI.h("div", { class: "history-controls" }, filter, FanboxUI.sortToggle(order, actions.onOrder, FanboxUI.t("jobs.history_sort")))), active ? FanboxUI.h("p", { class: "history-notice" }, FanboxUI.t("jobs.history_locked")) : null, FanboxUI.h("div", { class: "history-list" }, rows.length ? rows : FanboxUI.h("p", { class: "empty compact" }, FanboxUI.t("jobs.history_empty"))), FanboxUI.renderPagination(data, actions.onPage, FanboxUI.t("jobs.history_pagination")));
    }
    function renderBackupJobPage(job, creators, activeJob, actions) {
        const active = isActiveJob(job);
        const blocked = Boolean(activeJob && activeJob.job_id !== job.job_id);
        const plan = (job.events ?? []).find(item => item.kind === "plan_ready");
        const retryable = ["failed", "cancelled", "interrupted"].includes(job.status);
        const selectedCreators = requestCreators(job.request);
        const creatorNames = new Map(creators.map(item => [item.creator_id, item.name]));
        const controls = FanboxUI.h("div", { class: "job-actions" }, active && job.external ? FanboxUI.h("p", { class: "notice" }, FanboxUI.t("jobs.background_job_notice")) : null, active && !job.external ? FanboxUI.h("button", { type: "button", class: "danger", onclick: () => actions.onCancel(job.job_id) }, job.status === "cancelling" ? FanboxUI.t("jobs.stopping") : FanboxUI.t("jobs.stop")) : null, retryable ? FanboxUI.h("button", { type: "button", class: "retry", disabled: blocked,
            onclick: () => actions.onRetry(job.job_id) }, FanboxUI.t("jobs.retry_same")) : null, !active ? FanboxUI.h("button", { type: "button", disabled: blocked, onclick: actions.onNew }, FanboxUI.t("jobs.new_job")) : null, FanboxUI.h("button", { type: "button", class: "secondary", disabled: active, onclick: actions.onHistory }, FanboxUI.t("jobs.history")));
        return FanboxUI.h("section", { class: "page backup-page", "data-job-id": job.job_id }, jobPart(FanboxUI.h("header", { class: "heading job-heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP JOB"), FanboxUI.h("h1", {}, FanboxUI.t("jobs.job_title")), FanboxUI.h("p", {}, jobModeLabel(job))), FanboxUI.h("span", { class: `job-status status-${job.status}` }, statusText(job.status))), "header"), jobPart(activeJobNotice(blocked ? activeJob : null) || FanboxUI.h("div", { hidden: true }), "global-active"), jobPart(FanboxUI.h("section", { class: "job-scope" }, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP SCOPE"), FanboxUI.h("h2", {}, jobCreatorLabel(job, creators)), selectedCreators.length
            ? FanboxUI.h("ul", {}, selectedCreators.map(id => FanboxUI.h("li", {}, FanboxUI.h("strong", {}, creatorNames.get(id) || id), FanboxUI.h("span", {}, `@${id}`))))
            : FanboxUI.h("p", {}, FanboxUI.t("jobs.all_supporting"))), "scope"), jobPart(planSummary(plan, creators) || FanboxUI.h("div", { hidden: true }), "plan"), jobPart(currentActivity(job), "activity"), jobPart(FanboxUI.h("p", { class: "job-error", hidden: !job.error }, FanboxUI.h("strong", {}, FanboxUI.t("jobs.error_label")), job.error || ""), "error"), jobPart(FanboxUI.h("div", { class: "result-strip", hidden: !job.result }, job.result ? [
            FanboxUI.h("span", {}, FanboxUI.t("jobs.result_selected"), FanboxUI.h("strong", {}, job.result.selected ?? 0)),
            FanboxUI.h("span", {}, FanboxUI.t("jobs.result_success"), FanboxUI.h("strong", {}, job.result.success ?? 0)),
            FanboxUI.h("span", {}, FanboxUI.t("jobs.result_unchanged"), FanboxUI.h("strong", {}, job.result.unchanged ?? 0)),
            FanboxUI.h("span", {}, FanboxUI.t("jobs.result_failure"), FanboxUI.h("strong", {}, job.result.failure ?? 0)),
        ] : null), "result"), jobPart(controls, "actions"), jobPart(eventLog(job.events ?? []), "details"));
    }
    FanboxUI.renderBackupJobPage = renderBackupJobPage;
    function renderBackupFormPage(creators, defaults, activeJob, auth, actions) {
        const blocked = Boolean(activeJob);
        const selected = [];
        const dryRun = FanboxUI.h("input", { id: "backup-dry-run", type: "checkbox", checked: defaults.dryRun });
        const includeProfile = FanboxUI.h("input", { id: "backup-include-profile", type: "checkbox", checked: defaults.includeProfile });
        const includeFancard = FanboxUI.h("input", { id: "backup-include-fancard", type: "checkbox", checked: defaults.includeFancard });
        const maxPosts = FanboxUI.h("input", { id: "backup-max-posts", type: "number", min: 1, max: 100, value: defaults.maxPosts });
        const selectedList = FanboxUI.h("div", { class: "selected-creator-list" });
        const count = FanboxUI.h("strong", {}, FanboxUI.t("backup.selected_count", { count: 0 }));
        const input = FanboxUI.h("input", { type: "search", placeholder: FanboxUI.t("backup.search_placeholder"), autocomplete: "off",
            role: "combobox", "aria-label": FanboxUI.t("backup.search_label"), "aria-expanded": "false" });
        const menu = FanboxUI.h("div", { class: "creator-combobox-menu", role: "listbox", hidden: true });
        const combobox = FanboxUI.h("div", { class: "creator-combobox form-field" }, FanboxUI.h("span", {}, FanboxUI.t("backup.add_creator")), input, menu);
        let activeIndex = 0;
        let listeningOutside = false;
        const closeMenu = () => {
            menu.hidden = true;
            input.setAttribute("aria-expanded", "false");
            if (listeningOutside) {
                document.removeEventListener("pointerdown", handleOutsidePointer);
                listeningOutside = false;
            }
        };
        const handleOutsidePointer = (event) => {
            if (!combobox.isConnected || !combobox.contains(event.target))
                closeMenu();
        };
        const openMenu = () => {
            renderCandidates();
            menu.hidden = false;
            input.setAttribute("aria-expanded", "true");
            if (!listeningOutside) {
                document.addEventListener("pointerdown", handleOutsidePointer);
                listeningOutside = true;
            }
        };
        const renderSelected = () => {
            count.textContent = FanboxUI.t("backup.selected_count", { count: selected.length });
            selectedList.replaceChildren(...(selected.length ? selected.map(id => {
                const creator = creators.find(item => item.creator_id === id);
                return FanboxUI.h("div", { class: "selected-creator" }, FanboxUI.h("button", { type: "button", class: "remove-creator",
                    "aria-label": FanboxUI.t("backup.remove_creator", { name: creator?.name || id, creator_id: id }), onclick: () => {
                        selected.splice(selected.indexOf(id), 1);
                        renderSelected();
                        renderCandidates();
                    } }, "×"), FanboxUI.h("span", {}, FanboxUI.h("strong", {}, creator?.name || id), FanboxUI.h("small", {}, `@${id}`)));
            }) : [FanboxUI.h("p", { class: "empty compact" }, FanboxUI.t("backup.no_selection"))]));
        };
        const choose = (id) => {
            if (!selected.includes(id))
                selected.push(id);
            input.value = "";
            activeIndex = 0;
            renderSelected();
            renderCandidates();
            input.focus();
            closeMenu();
        };
        const renderCandidates = () => {
            const matches = filterBackupCreators(creators, input.value, selected);
            activeIndex = Math.min(activeIndex, Math.max(0, matches.length - 1));
            menu.replaceChildren(...(matches.length ? matches.map((item, index) => FanboxUI.h("button", { type: "button", role: "option",
                class: index === activeIndex ? "active" : "", "aria-selected": index === activeIndex ? "true" : "false",
                onclick: () => choose(item.creator_id) }, FanboxUI.h("strong", {}, item.name), FanboxUI.h("small", {}, `@${item.creator_id}`)))
                : [FanboxUI.h("p", { class: "empty compact" }, FanboxUI.t("backup.no_match"))]));
        };
        input.addEventListener("focus", openMenu);
        input.addEventListener("click", () => { if (menu.hidden)
            openMenu(); });
        input.addEventListener("input", () => { activeIndex = 0; openMenu(); });
        input.addEventListener("keydown", event => {
            const matches = filterBackupCreators(creators, input.value, selected);
            if (event.key === "Escape") {
                closeMenu();
                return;
            }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                activeIndex = Math.max(0, Math.min(matches.length - 1, activeIndex + (event.key === "ArrowDown" ? 1 : -1)));
                renderCandidates();
                return;
            }
            const candidate = matches[activeIndex];
            if (event.key === "Enter" && !menu.hidden && candidate) {
                event.preventDefault();
                choose(candidate.creator_id);
            }
        });
        renderSelected();
        const start = (mode, preview) => actions.onStart([...selected], preview, Number(maxPosts.value), mode, includeProfile.checked, includeFancard.checked);
        return FanboxUI.h("section", { class: "page backup-page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP CONTROL"), FanboxUI.h("h1", {}, FanboxUI.t("backup.title")), FanboxUI.h("p", {}, FanboxUI.t("backup.subtitle"))), FanboxUI.h("button", { type: "button", class: "primary", onclick: actions.onHistory }, FanboxUI.t("jobs.history"))), activeJobNotice(activeJob), auth.state !== "authenticated" && auth.state !== "locked" ? FanboxUI.h("section", { class: "backup-auth-notice", role: "status" }, FanboxUI.h("div", {}, FanboxUI.h("strong", {}, auth.state === "expired" ? FanboxUI.t("backup.auth_expired") : FanboxUI.t("backup.auth_check")), FanboxUI.h("p", {}, auth.message)), FanboxUI.h("button", { type: "button", onclick: actions.onSignIn }, FanboxUI.t("backup.go_sign_in"))) : null, FanboxUI.h("form", { class: "backup-form", onsubmit: (event) => { event.preventDefault(); if (!blocked)
                start("full", dryRun.checked); } }, combobox, FanboxUI.h("section", { class: "selected-creators", "aria-live": "polite" }, FanboxUI.h("div", { class: "selected-creators-heading" }, FanboxUI.h("span", {}, FanboxUI.t("backup.list_title")), count), selectedList), FanboxUI.h("label", {}, FanboxUI.h("span", {}, FanboxUI.t("backup.max_posts")), maxPosts), FanboxUI.h("label", { class: "checkbox" }, dryRun, FanboxUI.h("span", {}, FanboxUI.t("backup.dry_run"))), FanboxUI.h("label", { class: "checkbox" }, includeProfile, FanboxUI.h("span", {}, FanboxUI.t("backup.include_profile"))), FanboxUI.h("label", { class: "checkbox" }, includeFancard, FanboxUI.h("span", {}, FanboxUI.t("backup.include_fancard"))), FanboxUI.h("button", { type: "submit", class: "primary", disabled: blocked }, FanboxUI.t("backup.start_full")), FanboxUI.h("div", { class: "metadata-actions" }, FanboxUI.h("div", {}, FanboxUI.h("strong", {}, FanboxUI.t("backup.single_title")), FanboxUI.h("small", {}, FanboxUI.t("backup.single_hint"))), FanboxUI.h("div", { class: "metadata-buttons" }, FanboxUI.h("button", { type: "button", disabled: blocked,
            onclick: () => start("profile", false) }, FanboxUI.t("backup.include_profile")), FanboxUI.h("button", { type: "button", disabled: blocked, onclick: () => start("fancard", false) }, FanboxUI.t("backup.include_fancard"))))), FanboxUI.h("p", { class: "notice" }, FanboxUI.t("backup.single_notice")));
    }
    FanboxUI.renderBackupFormPage = renderBackupFormPage;
    function renderBackupHistoryPage(data, creators, filterValue, order, actions) {
        return FanboxUI.h("section", { class: "page backup-page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "JOB HISTORY"), FanboxUI.h("h1", {}, FanboxUI.t("jobs.history")), FanboxUI.h("p", {}, FanboxUI.t("backup.history_subtitle"))), FanboxUI.h("button", { type: "button", class: "primary", onclick: actions.onNew }, FanboxUI.t("jobs.new_job"))), jobHistory(data, null, creators, filterValue, order, actions));
    }
    FanboxUI.renderBackupHistoryPage = renderBackupHistoryPage;
    function verificationHistory(data, selectedId, order, actions) {
        const active = data.active;
        const rows = data.items.map(item => FanboxUI.h("button", { type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
            disabled: Boolean(active && item.job_id !== active.job_id), onclick: () => actions.onShow(item.job_id) }, FanboxUI.h("span", { class: `history-status status-${item.status}` }, statusText(item.status)), FanboxUI.h("span", { class: "history-main" }, FanboxUI.h("strong", {}, FanboxUI.t("jobs.kind_verify")), FanboxUI.h("small", {}, FanboxUI.formatDate(item.created_at))), FanboxUI.h("span", { class: "history-result" }, item.result
            ? item.result.passed ? FanboxUI.t("verify.passed") : FanboxUI.t("verify.issue_count", { count: item.result.issue_count ?? 0 })
            : item.error ? FanboxUI.t("jobs.view_error") : FanboxUI.t("jobs.view_progress"))));
        return FanboxUI.h("section", { class: "job-history" }, FanboxUI.h("div", { class: "history-heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "VERIFY HISTORY"), FanboxUI.h("h2", {}, FanboxUI.t("verify.history_title"))), FanboxUI.sortToggle(order, actions.onOrder, FanboxUI.t("verify.history_sort"))), active ? FanboxUI.h("p", { class: "history-notice" }, FanboxUI.t("verify.history_locked")) : null, FanboxUI.h("div", { class: "history-list" }, rows.length ? rows : FanboxUI.h("p", { class: "empty compact" }, FanboxUI.t("verify.history_empty"))), FanboxUI.renderPagination(data, actions.onPage, FanboxUI.t("verify.history_pagination")));
    }
    function renderMaintenancePage(job, history, order, activeJob, actions) {
        const active = Boolean(activeJob);
        const result = job?.result;
        const issues = result?.issues ?? [];
        const issueRows = issues.map(item => FanboxUI.h("li", {}, FanboxUI.h("strong", {}, item.reason), FanboxUI.h("code", {}, item.path), item.post_id ? FanboxUI.h("small", {}, `Post ${item.post_id}`) : null));
        return FanboxUI.h("section", { class: "page maintenance-page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "ARCHIVE MAINTENANCE"), FanboxUI.h("h1", {}, FanboxUI.t("verify.title")), FanboxUI.h("p", {}, FanboxUI.t("verify.subtitle"))), job ? FanboxUI.h("span", { class: `job-status status-${job.status}` }, statusText(job.status)) : null), activeJobNotice(activeJob), FanboxUI.h("section", { class: "maintenance-action" }, FanboxUI.h("div", {}, FanboxUI.h("h2", {}, activeJob?.kind === "verify" ? FanboxUI.t("verify.running") : activeJob ? FanboxUI.t("verify.other_job") : FanboxUI.t("verify.integrity")), FanboxUI.h("p", {}, FanboxUI.t("verify.hint"))), FanboxUI.h("button", { type: "button", class: "primary", disabled: active, onclick: actions.onStart }, activeJob?.kind === "verify" ? FanboxUI.t("verify.button_running") : activeJob ? FanboxUI.t("verify.button_blocked") : FanboxUI.t("verify.button_start"))), job?.error ? FanboxUI.h("p", { class: "job-error" }, FanboxUI.h("strong", {}, FanboxUI.t("jobs.error_label")), job.error) : null, verificationProgress(job), result ? FanboxUI.h("section", { class: `verification-result ${result.passed ? "passed" : "issues"}` }, FanboxUI.h("div", { class: "verification-summary" }, FanboxUI.h("strong", {}, result.passed ? FanboxUI.t("verify.passed") : FanboxUI.t("verify.issue_count", { count: result.issue_count ?? 0 })), FanboxUI.h("span", {}, result.passed ? FanboxUI.t("verify.passed_detail") : FanboxUI.t("verify.issues_detail"))), issueRows.length ? FanboxUI.h("ul", { class: "verification-issues" }, issueRows) : null, result.truncated ? FanboxUI.h("p", { class: "notice" }, FanboxUI.t("verify.truncated")) : null) : null, verificationHistory(history, job?.job_id ?? null, order, actions));
    }
    FanboxUI.renderMaintenancePage = renderMaintenancePage;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function startApp() {
        const appElement = document.getElementById("app");
        const searchElement = document.getElementById("search");
        const navElement = document.getElementById("nav");
        const tokenMeta = document.querySelector('meta[name="fanbox-session-token"]');
        if (!(appElement instanceof HTMLElement) || !(searchElement instanceof HTMLInputElement)
            || !(navElement instanceof HTMLElement) || !tokenMeta) {
            throw new Error("GUI 缺少必要的頁面元素");
        }
        const app = appElement;
        const search = searchElement;
        const nav = navElement;
        const sessionToken = tokenMeta.content;
        FanboxUI.setDisplayTimeZone(document.querySelector('meta[name="fanbox-timezone"]')?.content);
        FanboxUI.applyI18n(document);
        const state = FanboxUI.createInitialState();
        let jobTimer;
        let searchTimer;
        let currentLoad = null;
        function beginLoad() {
            currentLoad?.abort();
            if (jobTimer !== undefined)
                clearTimeout(jobTimer);
            const controller = new AbortController();
            currentLoad = controller;
            return { signal: controller.signal, live: () => currentLoad === controller && !controller.signal.aborted };
        }
        function loadFailed(load, error) {
            if (load.live() && !FanboxUI.isAbortError(error))
                errorView(error);
        }
        function optional(request) {
            return request.catch(error => {
                if (FanboxUI.isAbortError(error))
                    throw error;
                return null;
            });
        }
        document.addEventListener("click", event => FanboxUI.closeDropdownsOutside(event.target));
        function errorView(error) {
            app.replaceChildren(FanboxUI.renderError(error, refreshView));
        }
        function setActiveNav(view) {
            FanboxUI.setActiveNavigation(nav, view);
        }
        function setSearch(view) {
            FanboxUI.setSearchState(search, view, state.creatorTab);
        }
        let savedTheme = document.documentElement.dataset.theme ?? "auto";
        function setView(view) {
            currentLoad?.abort();
            if (jobTimer !== undefined)
                clearTimeout(jobTimer);
            document.documentElement.dataset.theme = savedTheme;
            state.view = view;
            state.current = null;
            state.page = 1;
            state.tag = "";
            if (view === "backup") {
                state.backupScreen = "form";
                state.backupJobId = null;
            }
            if (view !== "creator")
                state.creatorId = null;
            if (view !== "settings") {
                settingsPage = null;
                if (location.hash.startsWith("#settings"))
                    history.pushState(null, "", `${location.pathname}${location.search}`);
            }
            setActiveNav(view);
            setSearch(view);
            void refreshView();
        }
        function refreshView(showLoading = true) {
            if (state.view === "backup")
                return loadBackup(showLoading);
            if (state.view === "maintenance")
                return loadMaintenance(showLoading);
            if (state.view === "settings")
                return showLoading ? loadSettings() : refreshSettings();
            if (state.view === "creators")
                return loadCreators();
            if (state.view === "creator" && state.creatorId)
                return loadCreator(state.creatorId, state.creatorTab);
            return loadPosts();
        }
        function updateActiveJob(data) {
            state.activeJob = data.active;
            return state.activeJob;
        }
        function historyParams(kind, page, order, status = "all") {
            const params = new URLSearchParams({ kind, page: String(page), page_size: "20", order });
            if (status !== "all")
                params.set("status", status);
            return params;
        }
        function scheduleJobRefresh(authChecking = false) {
            if (jobTimer !== undefined)
                clearTimeout(jobTimer);
            if (state.activeJob && ["backup", "maintenance", "settings"].includes(state.view)
                || state.view === "settings" && authChecking) {
                jobTimer = window.setTimeout(() => void refreshView(false), 900);
            }
        }
        async function loadPosts() {
            const load = beginLoad();
            state.current = null;
            app.replaceChildren(FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_posts")));
            try {
                const params = new URLSearchParams({ page: String(state.page), page_size: "20", order: state.postOrder });
                if (state.q)
                    params.set("q", state.q);
                const data = await FanboxUI.getPosts(params, load.signal);
                if (!load.live())
                    return;
                state.page = data.page;
                app.replaceChildren(FanboxUI.renderPostListPage(data, {
                    onOpen: postId => void loadPost(postId),
                    onPage: page => { state.page = page; void loadPosts(); },
                    order: state.postOrder,
                    onOrder: order => { state.postOrder = order; state.page = 1; void loadPosts(); },
                }));
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        async function loadPost(postId, version = null) {
            const load = beginLoad();
            const creatorContent = state.view === "creator"
                ? app.querySelector(".creator-content") : null;
            const target = creatorContent ?? app;
            const creatorId = state.creatorId;
            const back = creatorContent && creatorId
                ? () => void loadCreator(creatorId, "posts") : () => void loadPosts();
            state.postNavigation = null;
            target.replaceChildren(FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_posts")));
            try {
                const params = new URLSearchParams({ order: state.postOrder });
                if (version !== null)
                    params.set("version", String(version));
                if (creatorContent && creatorId)
                    params.set("creator", creatorId);
                if (state.q)
                    params.set("q", state.q);
                if (creatorContent && state.tag)
                    params.set("tag", state.tag);
                const post = await FanboxUI.getPost(postId, params, load.signal);
                if (!load.live())
                    return;
                state.current = postId;
                state.postNavigation = post.navigation;
                const versionSelect = FanboxUI.customSelect({ id: "post-version", label: FanboxUI.t("common.version"), value: post.version,
                    options: post.versions.map(item => ({ value: item.number,
                        label: FanboxUI.t("common.version_option", { number: String(item.number).padStart(4, "0"),
                            time: FanboxUI.formatDate(item.captured_at) }) })),
                    onChange: value => void loadPost(postId, Number(value)) });
                target.replaceChildren(FanboxUI.renderPostReader(post, {
                    onBack: back,
                    onOpenPost: nextPostId => void loadPost(nextPostId),
                    versionSelect,
                }));
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        async function loadCreators() {
            const load = beginLoad();
            state.current = null;
            app.replaceChildren(FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_creators")));
            try {
                const data = await FanboxUI.getCreators(load.signal);
                if (!load.live())
                    return;
                app.replaceChildren(FanboxUI.renderCreatorsPage(data.items, state.q, creatorId => openCreator(creatorId)));
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        function openCreator(creatorId, tab = "profile") {
            state.view = "creator";
            state.creatorId = creatorId;
            state.creatorTab = tab;
            state.current = null;
            state.page = 1;
            state.q = "";
            state.tag = "";
            state.creator = null;
            state.creatorProfile = null;
            search.value = "";
            setActiveNav("creator");
            setSearch("creator");
            void loadCreator(creatorId, tab);
        }
        function switchCreatorTab(creatorId, tab) {
            state.creatorTab = tab;
            state.current = null;
            state.page = 1;
            state.q = "";
            state.tag = "";
            search.value = "";
            setSearch("creator");
            void loadCreator(creatorId, tab);
        }
        function creatorShell(creator, tab, content, profile = null) {
            return FanboxUI.renderCreatorShell(creator, tab, content, profile, {
                onBack: () => setView("creators"),
                onTab: nextTab => switchCreatorTab(creator.creator_id, nextTab),
            });
        }
        async function loadCreator(creatorId, tab = "profile", profileVersion = null) {
            const load = beginLoad();
            state.creatorTab = tab;
            setSearch("creator");
            try {
                let creator = state.creator?.creator_id === creatorId ? state.creator : null;
                let heroProfile = state.creatorProfile;
                if (!creator) {
                    app.replaceChildren(FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_creator_page")));
                    creator = await FanboxUI.getCreator(creatorId, load.signal);
                    heroProfile = creator.profile_available ? await FanboxUI.getCreatorProfile(creatorId, null, load.signal) : null;
                    if (!load.live() || state.creatorId !== creatorId)
                        return;
                    state.creator = creator;
                    state.creatorProfile = heroProfile;
                    app.replaceChildren(creatorShell(creator, tab, FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_content")), heroProfile));
                }
                let shell = app.querySelector(".creator-page");
                if (!shell || shell.dataset.creatorId !== creatorId) {
                    app.replaceChildren(creatorShell(creator, tab, FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_content")), heroProfile));
                    shell = app.querySelector(".creator-page");
                }
                if (!shell)
                    return;
                for (const button of shell.querySelectorAll("[data-creator-tab]")) {
                    button.classList.toggle("active", button.dataset.creatorTab === tab);
                }
                const contentRoot = shell.querySelector(".creator-content");
                if (!contentRoot)
                    return;
                contentRoot.replaceChildren(FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_content")));
                let content;
                if (tab === "posts") {
                    const params = new URLSearchParams({ creator: creatorId, page: String(state.page), page_size: "20",
                        order: state.postOrder });
                    if (state.q)
                        params.set("q", state.q);
                    if (state.tag)
                        params.set("tag", state.tag);
                    const data = await FanboxUI.getPosts(params, load.signal);
                    if (!load.live())
                        return;
                    state.page = data.page;
                    content = FanboxUI.renderCreatorPostList(data, {
                        onOpen: postId => void loadPost(postId),
                        onPage: page => { state.page = page; void loadCreator(creatorId, "posts"); },
                        order: state.postOrder,
                        onOrder: order => { state.postOrder = order; state.page = 1; void loadCreator(creatorId, "posts"); },
                        activeTag: state.tag,
                        onTag: tag => {
                            state.tag = tag;
                            state.page = 1;
                            history.pushState({ fanboxCreatorId: creatorId, fanboxCreatorTag: tag }, "", location.href);
                            void loadCreator(creatorId, "posts");
                        },
                    });
                }
                else if (tab === "fancards") {
                    const params = new URLSearchParams({ creator: creatorId });
                    if (state.q)
                        params.set("q", state.q);
                    const data = await FanboxUI.getFanCards(params, load.signal);
                    content = FanboxUI.renderFanCardList(data, { onOpen: (id, month) => void loadFancard(id, month) });
                }
                else {
                    let profile = heroProfile;
                    if (creator.profile_available && profileVersion !== null) {
                        profile = await FanboxUI.getCreatorProfile(creatorId, profileVersion, load.signal);
                    }
                    const versionSelect = profile ? FanboxUI.customSelect({ id: "profile-version", label: FanboxUI.t("creator.profile_version"), value: profile.version,
                        options: profile.versions.map(item => ({ value: item.number,
                            label: FanboxUI.t("common.version_option", { number: String(item.number).padStart(4, "0"),
                                time: FanboxUI.formatDate(item.captured_at) }) })),
                        onChange: value => void loadCreator(creatorId, "profile", Number(value)) }) : null;
                    content = FanboxUI.renderCreatorProfile(creator, profile, versionSelect);
                }
                if (!load.live() || state.creatorId !== creatorId || state.creatorTab !== tab)
                    return;
                contentRoot.replaceChildren(content);
            }
            catch (error) {
                if (state.creatorId !== creatorId)
                    return;
                loadFailed(load, error);
            }
        }
        async function loadFancard(creatorId, month, version = null) {
            const creatorContent = state.view === "creator"
                ? app.querySelector(".creator-content") : null;
            const load = beginLoad();
            const target = creatorContent ?? app;
            target.replaceChildren(FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_fancard")));
            try {
                const card = await FanboxUI.getFanCard(creatorId, month, version, load.signal);
                if (!load.live())
                    return;
                state.current = { type: "fancard", creatorId, month };
                const versionSelect = FanboxUI.customSelect({ id: "fancard-version", label: FanboxUI.t("common.version"), value: card.version,
                    options: card.versions.map(item => ({ value: item.number,
                        label: FanboxUI.t("common.version_option", { number: String(item.number).padStart(4, "0"),
                            time: FanboxUI.formatDate(item.captured_at) }) })),
                    onChange: value => void loadFancard(creatorId, month, Number(value)) });
                target.replaceChildren(FanboxUI.renderFanCardReader(card, {
                    onBack: () => void loadCreator(creatorId, "fancards"), versionSelect,
                }));
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        async function showJob(jobId, creators) {
            const load = beginLoad();
            try {
                const job = await FanboxUI.getJob(jobId, load.signal);
                if (!load.live())
                    return;
                state.backupScreen = "job";
                state.backupJobId = jobId;
                renderJob(job, creators);
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        function renderJob(job, creators) {
            if (jobTimer !== undefined)
                clearTimeout(jobTimer);
            const active = FanboxUI.isActiveJob(job);
            const page = FanboxUI.renderBackupJobPage(job, creators, state.activeJob, {
                onCancel: jobId => void cancelBackupJob(jobId),
                onRetry: jobId => void retryBackupJob(jobId),
                onNew: () => { state.backupScreen = "form"; state.backupJobId = null; void loadBackup(false); },
                onHistory: () => { state.backupScreen = "history"; state.backupJobId = null; void loadBackup(false); },
            });
            const currentPage = app.querySelector(".backup-page[data-job-id]");
            if (currentPage?.dataset.jobId === job.job_id)
                FanboxUI.updateJobPage(currentPage, page, active);
            else
                app.replaceChildren(page);
            scheduleJobRefresh();
        }
        function renderBackupForm(creators, settings, auth) {
            const value = settings.editable;
            app.replaceChildren(FanboxUI.renderBackupFormPage(creators, {
                dryRun: value.backup_defaults.dry_run,
                includeProfile: value.backup_defaults.include_profile,
                includeFancard: value.backup_defaults.include_fancard,
                maxPosts: value.sync.max_posts_per_run,
            }, state.activeJob, auth, {
                onStart: (creators, dryRun, maxPosts, mode, includeProfile, includeFancard) => void startBackup(creators, dryRun, maxPosts, mode, includeProfile, includeFancard),
                onHistory: () => { state.backupScreen = "history"; void loadBackup(false); },
                onSignIn: () => void navigate("settings", "account"),
            }));
            scheduleJobRefresh();
        }
        function renderBackupHistory(creators, history) {
            state.jobPage = history.page;
            app.replaceChildren(FanboxUI.renderBackupHistoryPage(history, creators, state.jobFilter, state.jobOrder, {
                onNew: () => { state.backupScreen = "form"; void loadBackup(false); },
                onShow: jobId => void showJob(jobId, creators),
                onFilter: value => { state.jobFilter = value; state.jobPage = 1; void loadBackup(false); },
                onOrder: order => { state.jobOrder = order; state.jobPage = 1; void loadBackup(false); },
                onPage: page => { state.jobPage = page; void loadBackup(false); },
            }));
        }
        async function loadBackup(showLoading = true) {
            const load = beginLoad();
            state.current = null;
            if (showLoading)
                app.replaceChildren(FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_jobs")));
            try {
                const [creatorData, jobData, settings, auth] = await Promise.all([
                    FanboxUI.getCreators(load.signal),
                    FanboxUI.getJobs(historyParams("backup", state.jobPage, state.jobOrder, state.jobFilter), load.signal),
                    FanboxUI.getSettings(load.signal), FanboxUI.getAuthStatus(sessionToken, load.signal),
                ]);
                if (!load.live())
                    return;
                updateActiveJob(jobData);
                const active = jobData.active?.kind === "backup" ? jobData.active : null;
                if (active) {
                    const job = await FanboxUI.getJob(active.job_id, load.signal);
                    if (!load.live())
                        return;
                    state.backupScreen = "job";
                    state.backupJobId = active.job_id;
                    renderJob({ ...job, external: active.external }, creatorData.items);
                }
                else if (state.backupScreen === "job" && state.backupJobId) {
                    const selected = await optional(FanboxUI.getJob(state.backupJobId, load.signal));
                    if (!load.live())
                        return;
                    if (selected)
                        renderJob(selected, creatorData.items);
                    else {
                        state.backupScreen = "form";
                        state.backupJobId = null;
                        renderBackupForm(creatorData.items, settings, auth);
                    }
                }
                else if (state.backupScreen === "history")
                    renderBackupHistory(creatorData.items, jobData);
                else
                    renderBackupForm(creatorData.items, settings, auth);
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        async function startBackup(creators, dryRun, maxPosts, mode = "full", includeProfile = true, includeFancard = true) {
            const load = beginLoad();
            try {
                const job = await FanboxUI.startBackupJob({ creators, dry_run: dryRun, max_posts: maxPosts, mode,
                    include_profile: includeProfile, include_fancard: includeFancard }, sessionToken);
                if (!load.live())
                    return;
                state.backupScreen = "job";
                state.backupJobId = job.job_id;
                await renderJobWithActive(job, load);
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        async function renderJobWithActive(job, load) {
            const [creatorData, jobData] = await Promise.all([FanboxUI.getCreators(load.signal), FanboxUI.getJobs(undefined, load.signal)]);
            if (!load.live())
                return;
            updateActiveJob(jobData);
            renderJob(job, creatorData.items);
        }
        async function cancelBackupJob(jobId) {
            const load = beginLoad();
            try {
                const job = await FanboxUI.cancelJob(jobId, sessionToken);
                if (load.live())
                    await renderJobWithActive(job, load);
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        async function retryBackupJob(jobId) {
            const load = beginLoad();
            try {
                const job = await FanboxUI.retryJob(jobId, sessionToken);
                if (load.live())
                    await renderJobWithActive(job, load);
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        function renderMaintenance(job, history) {
            if (jobTimer !== undefined)
                clearTimeout(jobTimer);
            state.verifyPage = history.page;
            app.replaceChildren(FanboxUI.renderMaintenancePage(job, history, state.verifyOrder, state.activeJob, {
                onStart: () => void startVerification(),
                onShow: jobId => { state.verifyJobId = jobId; void loadMaintenance(false); },
                onOrder: order => { state.verifyOrder = order; state.verifyPage = 1; void loadMaintenance(false); },
                onPage: page => { state.verifyPage = page; void loadMaintenance(false); },
            }));
            scheduleJobRefresh();
        }
        async function loadMaintenance(showLoading = true) {
            const load = beginLoad();
            state.current = null;
            if (showLoading)
                app.replaceChildren(FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_verify")));
            try {
                const [history, newest] = await Promise.all([
                    FanboxUI.getJobs(historyParams("verify", state.verifyPage, state.verifyOrder), load.signal),
                    FanboxUI.getJobs(historyParams("verify", 1, "desc"), load.signal),
                ]);
                if (!load.live())
                    return;
                const selectedId = (history.active?.kind === "verify" ? history.active.job_id : null)
                    ?? state.verifyJobId ?? newest.items[0]?.job_id ?? null;
                const selected = selectedId ? await optional(FanboxUI.getJob(selectedId, load.signal)) : null;
                if (!load.live())
                    return;
                updateActiveJob(history);
                renderMaintenance(selected, history);
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        async function startVerification() {
            const load = beginLoad();
            try {
                const job = await FanboxUI.startVerificationJob(sessionToken);
                if (!load.live())
                    return;
                state.verifyJobId = job.job_id;
                const history = await FanboxUI.getJobs(historyParams("verify", state.verifyPage, state.verifyOrder), load.signal);
                if (!load.live())
                    return;
                updateActiveJob(history);
                renderMaintenance(job, history);
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        let settingsPage = null;
        let settingsData = null;
        let settingsExtras = {};
        function settingsUrl(tab) {
            return `${location.pathname}${location.search}#settings/${tab}`;
        }
        function settingsTabFromHash() {
            const match = /^#settings(?:\/([a-z]+))?$/.exec(location.hash);
            if (!match)
                return null;
            return FanboxUI.isSettingsTab(match[1]) ? match[1] : "general";
        }
        async function confirmLeaveSettings() {
            if (state.view !== "settings" || !settingsPage?.isDirty())
                return true;
            return FanboxUI.confirmDialog({
                title: FanboxUI.t("settings.leave_title"),
                message: FanboxUI.t("settings.leave_message"),
                cancelLabel: FanboxUI.t("settings.leave_cancel"), confirmLabel: FanboxUI.t("settings.leave_confirm"), danger: true,
            });
        }
        async function navigate(view, tab = null) {
            if (!await confirmLeaveSettings())
                return;
            if (tab)
                state.settingsTab = tab;
            if (view === "settings")
                history.pushState(null, "", settingsUrl(state.settingsTab));
            setView(view);
        }
        async function switchSettingsTab(tab) {
            if (!await confirmLeaveSettings())
                return;
            history.pushState(null, "", settingsUrl(tab));
            openSettingsTab(tab);
        }
        function openSettingsTab(tab) {
            state.settingsTab = tab;
            document.documentElement.dataset.theme = savedTheme;
            void loadSettings();
        }
        const errorText = (error) => error instanceof Error ? error.message : String(error);
        function renderSettings(message) {
            if (!settingsData)
                return;
            const tab = state.settingsTab;
            settingsPage = FanboxUI.renderSettingsPage({
                data: settingsData, tab, message, activeJob: state.activeJob,
                onTab: next => void switchSettingsTab(next),
                onSave: patch => saveSettingsForm(patch),
                auth: null,
                account: {
                    onRefresh: () => void loadSettings(),
                    onLogin: () => authAction(async () => { await FanboxUI.startAuthLogin(sessionToken); }, FanboxUI.t("settings.login_opened")),
                    onCancel: jobId => authAction(async () => { await FanboxUI.cancelAuthLogin(jobId, sessionToken); }, FanboxUI.t("settings.login_cancelling")),
                    onLogout: () => authAction(async () => { await FanboxUI.logoutAuth(sessionToken); }, FanboxUI.t("settings.logged_out")),
                },
                schedule: settingsExtras.schedule ? { ...settingsExtras.schedule, actions: {
                        onPreview: schedule => FanboxUI.previewSchedule(schedule, sessionToken),
                        onRunNow: async () => {
                            try {
                                await FanboxUI.runScheduleNow(sessionToken);
                                setView("backup");
                                return null;
                            }
                            catch (error) {
                                return errorText(error);
                            }
                        },
                    } } : undefined,
                about: tab === "about" ? { info: settingsExtras.diagnostics ?? null, actions: {
                        onOpen: async (target) => {
                            try {
                                await FanboxUI.openDiagnosticsFolder(target, sessionToken);
                                return null;
                            }
                            catch (error) {
                                return errorText(error);
                            }
                        },
                    } } : undefined,
            });
            app.replaceChildren(settingsPage.node);
        }
        function checkAuth(load) {
            FanboxUI.getAuthStatus(sessionToken, load.signal).then(auth => {
                if (!load.live() || state.view !== "settings" || state.settingsTab !== "account")
                    return;
                settingsPage?.setAuth(auth);
                scheduleJobRefresh(auth.state === "checking");
            }).catch(error => {
                if (!load.live() || FanboxUI.isAbortError(error))
                    return;
                settingsPage?.setAuth({ state: "error", source: "none", message: FanboxUI.t("settings.auth_check_failed", { error: errorText(error) }),
                    can_login: false, can_logout: false, externally_managed: false, job: null });
            });
        }
        async function loadSettings(message = "", showLoading = true) {
            const load = beginLoad();
            const tab = state.settingsTab;
            state.current = null;
            settingsPage = null;
            if (showLoading)
                app.replaceChildren(FanboxUI.h("p", { class: "empty" }, FanboxUI.t("common.loading_settings")));
            try {
                const [data, jobData, schedule, diagnostics] = await Promise.all([
                    FanboxUI.getSettings(load.signal), FanboxUI.getJobs(undefined, load.signal),
                    tab === "backup" ? Promise.all([FanboxUI.getScheduleStatus(load.signal), FanboxUI.getCreators(load.signal)]) : null,
                    tab === "about" ? optional(FanboxUI.getDiagnostics(sessionToken, load.signal)) : null,
                ]);
                if (!load.live())
                    return;
                updateActiveJob(jobData);
                settingsData = data;
                settingsExtras = {
                    schedule: schedule ? { status: schedule[0], creators: schedule[1].items } : undefined,
                    diagnostics,
                };
                FanboxUI.setDisplayTimeZone(data.display.timezone);
                FanboxUI.applyTheme(data.editable.display.theme);
                savedTheme = document.documentElement.dataset.theme ?? "auto";
                renderSettings(message);
                if (tab === "account")
                    checkAuth(load);
                scheduleJobRefresh();
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        async function refreshSettings() {
            if (!settingsPage)
                return loadSettings("", false);
            const load = beginLoad();
            try {
                const jobData = await FanboxUI.getJobs(undefined, load.signal);
                if (!load.live())
                    return;
                updateActiveJob(jobData);
                settingsPage.setLocked(state.activeJob);
                if (state.settingsTab === "account")
                    checkAuth(load);
                scheduleJobRefresh();
            }
            catch (error) {
                loadFailed(load, error);
            }
        }
        async function authAction(action, message) {
            try {
                await action();
                if (state.view === "settings" && state.settingsTab === "account")
                    void loadSettings(message, false);
                return null;
            }
            catch (error) {
                return errorText(error);
            }
        }
        async function saveSettingsForm(patch) {
            const tab = state.settingsTab;
            try {
                const result = await FanboxUI.saveSettings(patch, sessionToken);
                if (state.view !== "settings" || state.settingsTab !== tab || !settingsData)
                    return null;
                const languageChanged = patch.display?.language !== undefined
                    && result.editable.display.language !== settingsData.editable.display.language;
                settingsData = { ...settingsData, editable: result.editable, display: result.display };
                FanboxUI.setDisplayTimeZone(result.display.timezone);
                if (patch.display?.theme !== undefined || patch.display?.colors !== undefined) {
                    FanboxUI.applyTheme(result.editable.display.theme);
                    savedTheme = document.documentElement.dataset.theme ?? "auto";
                    document.getElementById("custom-theme")?.setAttribute("href", `/theme.css?v=${Date.now()}`);
                }
                if (tab === "backup" && settingsExtras.schedule) {
                    const status = await optional(FanboxUI.getScheduleStatus());
                    if (status)
                        settingsExtras.schedule = { ...settingsExtras.schedule, status };
                    if (state.view !== "settings" || state.settingsTab !== tab)
                        return null;
                }
                renderSettings(languageChanged
                    ? FanboxUI.t("settings.saved_language")
                    : FanboxUI.t("settings.saved"));
                return null;
            }
            catch (error) {
                return errorText(error);
            }
        }
        search.addEventListener("input", () => {
            if (searchTimer !== undefined)
                clearTimeout(searchTimer);
            searchTimer = window.setTimeout(() => {
                state.q = search.value.trim();
                state.page = 1;
                void refreshView();
            }, 180);
        });
        nav.addEventListener("click", event => {
            const target = event.target instanceof Element
                ? event.target.closest("button[data-view]") : null;
            const view = target?.dataset.view;
            if (!view || !["posts", "creators", "backup", "maintenance", "settings"].includes(view))
                return;
            void (async () => {
                if (!await confirmLeaveSettings())
                    return;
                state.q = "";
                search.value = "";
                if (view === "settings")
                    history.pushState(null, "", settingsUrl(state.settingsTab));
                setView(view);
            })();
        });
        window.addEventListener("popstate", event => {
            const hashTab = settingsTabFromHash();
            if (state.view === "settings" && hashTab !== state.settingsTab) {
                const current = state.settingsTab;
                void confirmLeaveSettings().then(ok => {
                    if (!ok) {
                        history.pushState(null, "", settingsUrl(current));
                        return;
                    }
                    if (hashTab)
                        openSettingsTab(hashTab);
                    else
                        setView("posts");
                });
                return;
            }
            if (hashTab && state.view !== "settings") {
                state.settingsTab = hashTab;
                setView("settings");
                return;
            }
            if (state.view !== "creator" || state.creatorTab !== "posts" || !state.creatorId)
                return;
            const historyState = event.state;
            if (historyState?.fanboxCreatorId && historyState.fanboxCreatorId !== state.creatorId)
                return;
            state.tag = historyState?.fanboxCreatorTag ?? "";
            state.page = 1;
            void loadCreator(state.creatorId, "posts");
        });
        window.addEventListener("keydown", event => {
            if (["ArrowLeft", "ArrowRight"].includes(event.key)
                && typeof state.current === "string" && state.postNavigation) {
                const target = event.target;
                const interactive = target instanceof Element && (target.matches("input,textarea,select,button,a,summary,[contenteditable='true']")
                    || target.closest(".custom-select,.page-jump"));
                if (!interactive && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
                    const neighbor = event.key === "ArrowLeft"
                        ? state.postNavigation.previous : state.postNavigation.next;
                    if (neighbor) {
                        event.preventDefault();
                        void loadPost(neighbor.post_id);
                    }
                    return;
                }
            }
            if (event.key !== "Escape")
                return;
            if (FanboxUI.closeDropdownsAndFocus())
                return;
            if (state.current)
                void refreshView();
        });
        window.addEventListener("beforeunload", event => {
            if (state.view === "settings" && settingsPage?.isDirty()) {
                event.preventDefault();
                event.returnValue = "";
            }
        });
        const startTab = settingsTabFromHash();
        if (startTab)
            state.settingsTab = startTab;
        setView(startTab ? "settings" : "posts");
    }
    FanboxUI.startApp = startApp;
})(FanboxUI || (FanboxUI = {}));
if (typeof document !== "undefined" && document.getElementById("app"))
    FanboxUI.startApp();
var FanboxUI;
(function (FanboxUI) {
    function startDesktopOnboarding() {
        const root = document.getElementById("desktop-onboarding");
        const status = document.getElementById("desktop-status");
        if (!(root instanceof HTMLElement) || !(status instanceof HTMLElement))
            return;
        const bridge = window.__TAURI__;
        if (!bridge) {
            status.textContent = "此頁面必須由 FANBOX Archiver 桌面程式開啟。";
            status.classList.add("error");
            return;
        }
        const statusElement = status;
        const tauriCore = bridge.core;
        const buttons = [...root.querySelectorAll("button[data-command]")];
        async function launch(command) {
            for (const button of buttons)
                button.disabled = true;
            statusElement.textContent = command === "choose_existing_config"
                ? "請選擇既有的 config.yaml…"
                : command === "choose_archive_folder" ? "請選擇既有的 FANBOX 封存資料夾…"
                    : "正在建立新的本機資料…";
            statusElement.classList.remove("error");
            try {
                const result = await tauriCore.invoke(command);
                if (result === null) {
                    statusElement.textContent = "未選擇任何項目，你可以改用其他方式繼續。";
                    for (const button of buttons)
                        button.disabled = false;
                    return;
                }
                statusElement.textContent = `正在啟動本機伺服器：${result.config_path}`;
            }
            catch (error) {
                statusElement.textContent = error instanceof Error ? error.message : String(error);
                statusElement.classList.add("error");
                for (const button of buttons)
                    button.disabled = false;
            }
        }
        root.addEventListener("click", event => {
            const button = event.target instanceof Element
                ? event.target.closest("button[data-command]") : null;
            if (button?.dataset.command)
                void launch(button.dataset.command);
        });
    }
    if (typeof document !== "undefined" && document.getElementById("desktop-onboarding")) {
        startDesktopOnboarding();
    }
})(FanboxUI || (FanboxUI = {}));
