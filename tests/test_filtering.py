import pytest

from vinnytsia_monitor.pipeline.engine import evaluate
from vinnytsia_monitor.pipeline.models import Label


def test_city_shelter_notice_is_published(catalog):
    decision = evaluate("Вінниця також перебувайте в безпечному місці", catalog)

    assert decision.should_forward
    assert decision.geographically_relevant
    assert decision.label is Label.VINNYTSIA_RELEVANT
    assert "vinnytsia" in decision.location_ids
    assert "Local Alert" in decision.matched_rules
    assert any(reason.startswith("Accepted:") for reason in decision.reasons)


@pytest.mark.parametrize(
    "text",
    [
        "Курсом на Писарівку/Вінницькі Хутори",
        "Шахед летить на Вінницю",
        "БПЛА в напрямку Зарванців",
    ],
)
def test_heading_toward_a_configured_place_is_published(catalog, text):
    decision = evaluate(text, catalog)

    assert decision.geographically_relevant
    assert decision.should_forward
    assert decision.label is Label.VINNYTSIA_RELEVANT
    assert decision.safety_hits == ()
    if "Писарівку" in text:
        assert decision.location_ids[0] == "vinnytski_khutory"
        assert "pysarivka" in decision.location_ids
        assert any(reason.startswith("Geographic match: Вінницькі Хутори") for reason in decision.reasons)
        assert any(reason.startswith("Also named: Писарівка") for reason in decision.reasons)


def test_heading_toward_another_town_is_not_local(catalog):
    decision = evaluate("Курсом на Жмеринку", catalog)

    assert decision.should_forward is False
    assert decision.geographically_relevant is False
    assert decision.label is Label.OTHER_REGION


def test_nationwide_alert_does_not_match(catalog):
    decision = evaluate("Повітряна тривога по всій Україні", catalog)

    assert decision.should_forward is False
    assert decision.geographically_relevant is False
    assert decision.label is Label.UKRAINE_GENERAL


def test_other_cities_in_the_oblast_do_not_match(catalog):
    decision = evaluate("Жмеринка, Калинівка, Хмільник", catalog)

    assert decision.should_forward is False
    assert decision.label is Label.OTHER_REGION
    assert decision.location_ids == ()


def test_oblast_without_the_city_does_not_match(catalog):
    decision = evaluate("Вінницька область", catalog)

    assert decision.should_forward is False
    assert decision.geographically_relevant is False
    assert decision.label is Label.OTHER_REGION


def test_city_mention_inside_an_oblast_notice_still_matches(catalog):
    decision = evaluate("У Вінниці та Вінницькій області тривога", catalog)

    assert decision.should_forward
    assert decision.label is Label.VINNYTSIA_RELEVANT
    assert "vinnytsia" in decision.location_ids


def test_adjective_alone_is_not_the_city(catalog):
    decision = evaluate("Вінницькі новини сьогодні", catalog)

    assert decision.label is Label.UNCERTAIN
    assert decision.should_forward is False


def test_district_without_the_city_is_regional(catalog):
    decision = evaluate("Вінницький район без деталей", catalog)

    assert decision.label is Label.OTHER_REGION
    assert decision.should_forward is False


@pytest.mark.parametrize(
    "text",
    [
        "у Вінниці відбій тривоги",
        "В Виннице тревога",
        "Stay inside in Vinnytsia",
        "ВІННИЦЯ",
        "Він\u200bниця також перебувайте в укритті",
        "Стрижавка: перебувайте в укритті",
        "біля Агрономічного тихо",
        "Лука–Мелешківська: тривога",
        "мешканців Зарванців просять пройти в укриття",
        "Якушинці залишаються в укритті",
        "Курсом на Луку",
        "у Бучмах тривога",
        "Тяжилів, залишайтесь в укритті",
        "рух Немирівським шосе",
        "на Замості вибухи",
        "ТЯЖИЛІВ / ЧЕХОВА / МАСЛОЖИР",
        "ЛУКА / ХУТОРИ / АКАДЕМІЧНИЙ / ЦАРИНА / СТАРЕ МІСТО / ПОДІЛЛЯ",
    ],
)
def test_inflection_spelling_and_nearby_places_match(catalog, text):
    decision = evaluate(text, catalog)

    assert decision.geographically_relevant
    assert decision.should_forward
    assert decision.label is Label.VINNYTSIA_RELEVANT


def test_nearby_place_does_not_require_an_alert_keyword(catalog):
    decision = evaluate("Вінницькі Хутори, залишайтесь в укритті", catalog)

    assert decision.should_forward
    assert decision.location_ids == ("vinnytski_khutory",)


def test_threat_and_city_matches_the_all_rule(catalog):
    decision = evaluate("Є загроза для Вінниці", catalog)

    assert decision.should_forward
    assert "Relevant Event" in decision.matched_rules


def test_threat_without_the_city_is_not_enough(catalog):
    decision = evaluate("Є загроза для Жмеринки", catalog)

    assert decision.should_forward is False
    assert decision.label is Label.OTHER_REGION
    assert "Relevant Event" not in decision.matched_rules


def test_keyword_inside_a_longer_word_does_not_exclude_the_city(catalog):
    decision = evaluate("протест у Вінниці завершився спокійно", catalog)

    assert decision.should_forward


def test_drill_wording_is_not_published(catalog):
    training = evaluate("навчальна тривога у Вінниці", catalog)
    drill = evaluate("тест у Писарівці", catalog)

    assert training.geographically_relevant
    assert training.should_forward is False
    assert training.label is Label.VINNYTSIA_RELEVANT
    assert any("training_uk" in reason for reason in training.reasons)

    assert drill.should_forward is False
    assert any("тест" in reason for reason in drill.reasons)
    assert any("Nearby Locations (тест)" in reason for reason in drill.reasons)


def test_coordinates_are_not_published(catalog):
    decision = evaluate("Вінниця 49.2331, 28.4682", catalog)

    assert decision.geographically_relevant
    assert decision.should_forward is False
    assert decision.label is Label.SENSITIVE_OPERATIONAL_DETAILS
    assert "coordinate_pair" in decision.safety_hits


def test_empty_and_unknown_text_stay_unpublished(catalog):
    empty = evaluate("   ", catalog)
    unknown = evaluate("тихий вечір", catalog)

    assert empty.label is Label.UNCERTAIN
    assert unknown.label is Label.UNCERTAIN
    assert empty.should_forward is False
    assert unknown.should_forward is False


def test_channel_footer_is_not_a_vinnytsia_trigger(catalog):
    footer = "👉 Термінові новини Вінниці (https://t.me/+lmOWbg1mAnE1YWUy) 👈"

    only_footer = evaluate(footer, catalog)
    other_town = evaluate(f"Жмеринка\n{footer}", catalog)
    local_alert = evaluate(f"Реактивний Шахед на ТЯЖИЛІВ / ЧЕХОВА\n{footer}", catalog)

    assert only_footer.should_forward is False
    assert "vinnytsia" not in only_footer.location_ids
    assert other_town.should_forward is False
    assert other_town.label is Label.OTHER_REGION
    assert local_alert.should_forward is True
    assert "tiazhyliv" in local_alert.location_ids
    assert "chekhova" in local_alert.location_ids
    assert "vinnytsia" not in local_alert.location_ids


def test_the_same_text_always_gets_the_same_decision(catalog):
    text = "У Вінниці перебувайте в безпечному місці"
    assert evaluate(text, catalog) == evaluate(text, catalog)
