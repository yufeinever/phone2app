import os

import pytest

from phone2app.appium_ext.driver import appium_session, AppiumDependencyError
from phone2app.appium_ext.input_providers import build_input_provider
from phone2app.appium_ext.pages import ChatPage


pytestmark = pytest.mark.skipif(
    os.environ.get("PHONE2APP_APPIUM_E2E") != "1",
    reason="Set PHONE2APP_APPIUM_E2E=1 to run real-device Appium tests.",
)


def test_chat_feature_carousel_and_attachment_sheet():
    try:
        with appium_session("configs/appium.yaml") as driver:
            page = ChatPage(driver).wait_loaded()
            carousel = page.feature_carousel()
            assert "音视频通话" in carousel.visible_items()
            sheet = page.open_attachment_sheet()
            sheet.cancel()
    except AppiumDependencyError as exc:
        pytest.skip(str(exc))


def test_open_and_exit_ai_call():
    try:
        with appium_session("configs/appium.yaml") as driver:
            page = ChatPage(driver).wait_loaded()
            call = page.open_av_call()
            call.exit_call()
    except AppiumDependencyError as exc:
        pytest.skip(str(exc))


def test_chinese_input_provider_smoke():
    try:
        with appium_session("configs/appium.yaml") as driver:
            provider = build_input_provider("fastinput_ime", serial=os.environ.get("ANDROID_SERIAL"))
            page = ChatPage(driver).wait_loaded()
            page.enter_text("你好，这是中文输入测试。", provider=provider)
    except AppiumDependencyError as exc:
        pytest.skip(str(exc))
