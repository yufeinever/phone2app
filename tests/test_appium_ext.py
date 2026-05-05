from phone2app.appium_ext.base_page import SWIPE_FEATURES_LEFT, SWIPE_FEATURES_RIGHT
from phone2app.appium_ext.input_providers import build_input_provider, AppiumTextInput
from phone2app.appium_ext.locators import accessibility, text_exact, xpath_literal


def test_xpath_literal_handles_quotes():
    assert xpath_literal("hello") == "'hello'"
    assert xpath_literal('he"llo') == "'he\"llo'"
    assert xpath_literal("he'llo") == '"he\'llo"'
    assert xpath_literal('a\'b"c').startswith("concat(")


def test_locator_builders():
    assert accessibility("音视频通话").as_tuple() == ("accessibility id", "音视频通话")
    assert text_exact("最近").value == "//*[@text='最近']"


def test_swipe_plan_pixels():
    assert SWIPE_FEATURES_LEFT.to_pixels(1080, 2244) == (928, 2019, 194, 2019, 450)
    assert SWIPE_FEATURES_RIGHT.to_pixels(1080, 2244) == (194, 2019, 928, 2019, 450)


def test_input_provider_factory_appium():
    assert isinstance(build_input_provider("appium"), AppiumTextInput)
