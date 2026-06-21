from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def test_app_starts_without_prefilled_folder() -> None:
    app = AppTest.from_file("app.py", default_timeout=30).run(timeout=30)

    assert not app.exception
    assert app.title[0].value == "DHTOL Analyzer"
    assert app.text_input[0].label == "Testlauf-Ordner"
    assert app.text_input[0].value == ""
    assert any(message.value == "Testlauf-Ordner eingeben." for message in app.info)


@pytest.mark.skipif(
    not any(Path.cwd().glob("*.mtpx")),
    reason="Echte Testdaten liegen nicht im Code-Ordner.",
)
def test_app_loads_entered_folder() -> None:
    app = AppTest.from_file("app.py", default_timeout=30).run(timeout=30)
    app.text_input[0].set_value(str(Path.cwd())).run(timeout=30)

    assert not app.exception
    assert any(metric.label == "Boards" and metric.value == "8" for metric in app.metric)
    assert not any(button.label == "Cache leeren" for button in app.button)
    assert not any(
        checkbox.label in {
            "Weitere Testläufe anzeigen",
            "Temperatur-Glitch-Analyse starten",
        }
        for checkbox in app.checkbox
    )
    assert not any(selectbox.label == "Testlauf" for selectbox in app.selectbox)
    board_selector = next(
        selectbox for selectbox in app.selectbox if selectbox.label == "Board"
    )
    assert "Alle Boards" in board_selector.options
    assert all(
        option.startswith(("🔴 Fehler", "🟡 Temperaturfehler", "🟢 OK"))
        for option in board_selector.options
        if option != "Alle Boards"
    )
    assert [tab.label for tab in app.tabs] == [
        "Übersicht",
        "Board-Detail",
        "Zonenstrom",
        "Fehler / TTF",
    ]
