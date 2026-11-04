//! Interface text of the desktop shell's own screens (archive selection, startup errors, menu).
//!
//! These screens appear before the local server runs, so they cannot ask it for a catalog.
//! The four shipped catalogs are embedded at build time (the same files the server uses, so
//! `release:check` covers them) and only their `desktop.*` messages are kept. The language
//! follows the Windows display language with the same rules as the `auto` setting: any
//! Chinese variant reads Traditional Chinese, Japanese, Korean and English map to their own
//! catalog, and everything else falls back to English.

use std::{collections::BTreeMap, sync::OnceLock};

use serde::Serialize;

const BASE_LOCALE: &str = "zh-Hant";
const FALLBACK_LOCALE: &str = "en";
const PREFIX: &str = "desktop.";
const CATALOGS: [(&str, &str); 4] = [
    ("zh-Hant", include_str!("../../src/fanbox_archiver/locales/zh-Hant.json")),
    ("en", include_str!("../../src/fanbox_archiver/locales/en.json")),
    ("ja", include_str!("../../src/fanbox_archiver/locales/ja.json")),
    ("ko", include_str!("../../src/fanbox_archiver/locales/ko.json")),
];

/// What the startup page loads: its language tag and the desktop messages in that language.
#[derive(Clone, Debug, Serialize)]
pub struct DesktopMessages {
    pub locale: &'static str,
    pub messages: BTreeMap<String, String>,
}

/// The supported locale for a BCP 47 tag such as `zh-TW`, `ja-JP` or `fr-FR`.
pub fn match_locale(tag: &str) -> &'static str {
    let language = tag.trim().to_ascii_lowercase().replace('_', "-");
    match language.split('-').next().unwrap_or_default() {
        "zh" => BASE_LOCALE,
        "en" => "en",
        "ja" => "ja",
        "ko" => "ko",
        _ => FALLBACK_LOCALE,
    }
}

fn desktop_messages_of(locale: &str) -> BTreeMap<String, String> {
    let source = CATALOGS
        .iter()
        .find(|(name, _)| *name == locale)
        .map(|(_, source)| *source)
        .unwrap_or(CATALOGS[0].1);
    let parsed: BTreeMap<String, serde_json::Value> = serde_json::from_str(source).unwrap_or_default();
    parsed
        .into_iter()
        .filter(|(key, _)| key.starts_with(PREFIX))
        .filter_map(|(key, value)| value.as_str().map(|text| (key, text.to_owned())))
        .collect()
}

/// The desktop messages for `locale`, with the base catalog filling any gap.
pub fn messages_for(locale: &'static str) -> DesktopMessages {
    let mut messages = desktop_messages_of(BASE_LOCALE);
    messages.extend(desktop_messages_of(locale));
    DesktopMessages { locale, messages }
}

#[cfg(windows)]
fn system_language() -> Option<String> {
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetUserDefaultUILanguage() -> u16;
        fn LCIDToLocaleName(locale: u32, name: *mut u16, length: i32, flags: u32) -> i32;
    }
    let mut buffer = [0u16; 85];
    // SAFETY: both calls only read the current user's settings and write within `buffer`.
    let written = unsafe {
        let language = GetUserDefaultUILanguage();
        LCIDToLocaleName(u32::from(language), buffer.as_mut_ptr(), buffer.len() as i32, 0)
    };
    (written > 1).then(|| String::from_utf16_lossy(&buffer[..written as usize - 1]))
}

#[cfg(not(windows))]
fn system_language() -> Option<String> {
    ["LC_ALL", "LC_MESSAGES", "LANG"]
        .iter()
        .filter_map(|name| std::env::var(name).ok())
        .map(|value| value.split('.').next().unwrap_or_default().to_owned())
        .find(|value| !value.is_empty() && value != "C" && value != "POSIX")
}

/// The messages in the Windows display language, resolved once per run.
pub fn current() -> &'static DesktopMessages {
    static CURRENT: OnceLock<DesktopMessages> = OnceLock::new();
    CURRENT.get_or_init(|| messages_for(system_language().as_deref().map_or(FALLBACK_LOCALE, match_locale)))
}

/// One desktop message in the current language (the key itself if a catalog lacks it).
pub fn text(key: &str) -> String {
    current().messages.get(key).cloned().unwrap_or_else(|| key.to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn locale_follows_the_auto_rules() {
        assert_eq!(match_locale("zh-TW"), "zh-Hant");
        assert_eq!(match_locale("zh-CN"), "zh-Hant");
        assert_eq!(match_locale("ja-JP"), "ja");
        assert_eq!(match_locale("ko_KR"), "ko");
        assert_eq!(match_locale("en-GB"), "en");
        assert_eq!(match_locale("fr-FR"), "en");
        assert_eq!(match_locale(""), "en");
    }

    #[test]
    fn every_catalog_has_every_desktop_message() {
        let base = desktop_messages_of(BASE_LOCALE);
        assert!(base.len() >= 30, "desktop messages missing from the base catalog");
        for (locale, _) in CATALOGS {
            let messages = desktop_messages_of(locale);
            assert_eq!(messages.keys().collect::<Vec<_>>(), base.keys().collect::<Vec<_>>(), "{locale}");
        }
        assert_eq!(messages_for("en").messages["desktop.menu_archive"], "Archive");
        assert_eq!(messages_for("ko").messages["desktop.menu_archive"], "아카이브");
    }
}
