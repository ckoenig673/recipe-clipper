import importlib.util
from pathlib import Path
import sys
import types


class _StubReader:
    def __init__(self, *_args, **_kwargs):
        pass


def _load_module():
    stub_easyocr = types.SimpleNamespace(Reader=lambda *_args, **_kwargs: _StubReader())
    sys.modules.setdefault("easyocr", stub_easyocr)

    module_path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("ocr_worker_main", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_normalize_ocr_text_fixes_fraction_14_teaspoon():
    module = _load_module()

    text = module.normalize_ocr_text("14 teaspoon ground cinnamon")

    assert text == "1/4 teaspoon ground cinnamon"


def test_normalize_ocr_text_fixes_fraction_1_over_1_cup():
    module = _load_module()

    text = module.normalize_ocr_text("1/1 cup sour cream")

    assert text == "1/2 cup sour cream"


def test_normalize_ocr_text_fixes_fraction_y_cup():
    module = _load_module()

    text = module.normalize_ocr_text("Y cup oats")

    assert text == "1/3 cup oats"


def test_normalize_ocr_text_fixes_fraction_y4_teaspoon():
    module = _load_module()

    text = module.normalize_ocr_text("Y4 teaspoon cinnamon")

    assert text == "1/4 teaspoon cinnamon"


def test_normalize_ocr_text_adds_missing_quantity_for_package():
    module = _load_module()

    text = module.normalize_ocr_text("package (9 ounces)")

    assert text == "1 package (9 ounces)"


def test_normalize_ocr_text_keeps_existing_package_quantity():
    module = _load_module()

    text = module.normalize_ocr_text("2 packages (9 ounces)")

    assert text == "2 packages (9 ounces)"


def test_normalize_ocr_text_fixes_temperature_3508f():
    module = _load_module()

    text = module.normalize_ocr_text("Bake at 3508F for 30 minutes")

    assert text == "Bake at 350°F for 30 minutes"


def test_normalize_ocr_text_fixes_four_and_cinnamon_phrase():
    module = _load_module()

    text = module.normalize_ocr_text("Combine oats, brown sugar; four and cinnamon in small bowl")

    assert text == "Combine oats, brown sugar; flour and cinnamon in small bowl"


def test_normalize_ocr_text_fixes_four_comma_and_cinnamon_phrase():
    module = _load_module()

    text = module.normalize_ocr_text("Combine oats, brown sugar, four, and cinnamon")

    assert text == "Combine oats, brown sugar, flour, and cinnamon"


def test_normalize_ocr_text_fixes_suger():
    module = _load_module()

    text = module.normalize_ocr_text("suger")

    assert text == "sugar"


def test_normalize_ocr_text_fixes_browm_sugar():
    module = _load_module()

    text = module.normalize_ocr_text("browm sugar")

    assert text == "brown sugar"


def test_normalize_ocr_text_does_not_change_bake_four_minutes():
    module = _load_module()

    text = module.normalize_ocr_text("Bake four minutes")

    assert text == "Bake four minutes"


def test_raw_text_remains_unchanged_while_text_is_cleaned():
    module = _load_module()

    raw_text = module.clean_text("14 teaspoon ground cinnamon")
    cleaned_text = module.normalize_ocr_text(raw_text)

    assert raw_text == "14 teaspoon ground cinnamon"
    assert cleaned_text == "1/4 teaspoon ground cinnamon"
