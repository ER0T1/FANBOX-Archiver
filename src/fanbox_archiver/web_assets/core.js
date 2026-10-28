"use strict";
var FanboxUI;
(function (FanboxUI) {
    function createInitialState() {
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
    FanboxUI.createInitialState = createInitialState;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    const dateFormatter = new Intl.DateTimeFormat("zh-TW", {
        timeZone: "Asia/Taipei",
        dateStyle: "medium",
        timeStyle: "short",
    });
    function formatDate(value) {
        return value ? dateFormatter.format(new Date(value)) : "—";
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
            return "檔位未記錄";
        return Number(value) <= 0 ? "全體公開" : `¥${Number(value).toLocaleString()}`;
    }
    FanboxUI.feeLabel = feeLabel;
})(FanboxUI || (FanboxUI = {}));
