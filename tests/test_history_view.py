import flet as ft

from history_view import build_history_drawer, history_notice_visible


def test_history_scope_notice_is_hidden_on_both_calculators() -> None:
    assert history_notice_visible("REGULAR MODE") is False
    assert history_notice_visible("SCIENTIFIC MODE") is False


def test_history_scope_notice_is_shown_on_other_pages() -> None:
    for status in ("UNIT CONVERSION", "CURRENCY CONVERSION", "PI CALCULATION"):
        assert history_notice_visible(status) is True


def test_history_scope_notice_is_at_the_top_of_the_drawer() -> None:
    notice = ft.Text(
        "History only applies to the Regular and Scientific Calculators.",
        visible=False,
    )
    drawer = build_history_drawer(ft.Column(), notice, lambda event: event)
    notice_container = drawer.controls[1]

    assert isinstance(notice_container, ft.Container)
    assert notice_container.content is notice
