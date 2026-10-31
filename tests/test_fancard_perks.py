from fanbox_archiver.fancard_perks import normalize_fancard_perks


def test_normalizes_known_perk_states_conservatively():
    perks = normalize_fancard_perks([
        {"name": "discord", "available": True, "supporterAccessible": True},
        {"name": "discord", "available": True, "supporterAccessible": False},
        {"name": "discord", "available": False, "supporterAccessible": True},
        {"name": "discord", "available": True},
        {"name": "discord"},
    ])

    assert [item["status"] for item in perks] == [
        "accessible", "inaccessible", "unavailable", "available", "unknown",
    ]
    assert all(item["label"] == "Discord 特典" for item in perks)
    assert "加入連結" in perks[0]["description"]


def test_unknown_and_legacy_perks_have_safe_fallback_without_raw_fields():
    perks = normalize_fancard_perks([
        "原圖下載",
        {"name": "future-benefit", "available": "yes", "supporterAccessible": None,
         "token": "must-not-leak", "url": "https://example.test/?token=secret"},
        None,
        42,
    ])

    assert [item["label"] for item in perks] == ["原圖下載", "future-benefit"]
    assert [item["status"] for item in perks] == ["unknown", "unknown"]
    assert "must-not-leak" not in str(perks)
    assert "secret" not in str(perks)


def test_non_list_perks_are_ignored():
    assert normalize_fancard_perks(None) == []
    assert normalize_fancard_perks({"name": "discord"}) == []
