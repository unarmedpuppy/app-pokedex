#!/usr/bin/env python3
"""
Pokemon HOME Collection Capture
================================
Standalone Appium script — no LLM in the loop.
Runs phases independently; state is tracked in the DB so runs can be resumed.

Usage:
    python capture.py [--phase 1|2|3] [--box N] [--slot N]

Phases:
    1  Navigate to boxes, take a screenshot of the current box grid (verify nav works)
    2  Capture all box grid screenshots (swipe through all boxes)
    3  Capture per-Pokemon detail screenshots (tap each slot, screenshot, back)

After capture, run parse.py to extract metadata with Claude vision.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException, TimeoutException

sys.path.insert(0, str(Path(__file__).parent.parent))
from collection.schema import init_db, upsert_pokemon, get_state, set_state, IMAGES_DIR, DB_PATH

# ── Config ────────────────────────────────────────────────────────────────────

DEVICE_UDID = "ae7b05b8416a2adb0c2688a2da14d9fd2aadd7c9"
POKEMON_HOME_BUNDLE = "jp.pokemon.pokemonhome"
APPIUM_URL = "http://127.0.0.1:4723/wd/hub"
WDA_URL = "http://127.0.0.1:8100"

COLS_PER_BOX = 6
ROWS_PER_BOX = 5
SLOTS_PER_BOX = COLS_PER_BOX * ROWS_PER_BOX  # 30


# ── Driver ────────────────────────────────────────────────────────────────────

def create_driver() -> webdriver.Remote:
    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.device_name = "iPhone"
    options.udid = DEVICE_UDID
    options.automation_name = "XCUITest"
    options.bundle_id = POKEMON_HOME_BUNDLE
    options.no_reset = True
    options.new_command_timeout = 120
    options.webdriveragent_url = WDA_URL
    return webdriver.Remote(APPIUM_URL, options=options)


# ── Primitives ────────────────────────────────────────────────────────────────

def tap(driver, x, y):
    driver.execute_script("mobile: tap", {"x": x, "y": y})


def swipe_left(driver, w, h):
    """Swipe left across the box area to go to the next box."""
    driver.execute_script("mobile: swipe", {
        "startX": w * 0.75, "startY": h * 0.45,
        "endX": w * 0.25,   "endY": h * 0.45,
        "duration": 400,
    })


def screenshot(driver, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(path))
    print(f"  [ss] {path}")
    return path


def try_find(driver, by, value):
    try:
        return driver.find_element(by, value)
    except NoSuchElementException:
        return None


def try_tap_by_label(driver, *labels) -> bool:
    for label in labels:
        el = try_find(driver, AppiumBy.ACCESSIBILITY_ID, label)
        if el:
            el.click()
            print(f"  [tap] found element: '{label}'")
            return True
    return False


def try_tap_by_xpath(driver, xpath) -> bool:
    el = try_find(driver, AppiumBy.XPATH, xpath)
    if el:
        el.click()
        print(f"  [tap] found xpath: {xpath}")
        return True
    return False


def page_source_labels(driver) -> list[str]:
    """Return all accessibility labels on screen for debugging."""
    try:
        src = driver.page_source
        import re
        return re.findall(r'label="([^"]+)"', src)
    except Exception:
        return []


# ── Phase 0: Navigate to boxes ────────────────────────────────────────────────

def dismiss_ios_dialogs(driver):
    """Dismiss any iOS system dialogs (Software Update, permissions, etc.)."""
    dismiss_labels = ["Later", "Not Now", "Allow", "OK", "Close", "Cancel", "Dismiss"]
    for label in dismiss_labels:
        el = try_find(driver, AppiumBy.ACCESSIBILITY_ID, label)
        if el:
            el.click()
            print(f"  [dialog] dismissed: '{label}'")
            time.sleep(1.5)
            return True
    return False


def navigate_to_boxes(driver) -> bool:
    """
    Navigate from the app launch screen into the Pokemon boxes view.
    Returns True if we successfully reach a boxes-like screen.

    Pokemon HOME navigation path (v3.x):
      Launch → (TAP TO START) → Main menu → My Pokemon / Pokemon tab → Boxes
    """
    w, h = driver.get_window_size()["width"], driver.get_window_size()["height"]

    # Step 1: Dismiss any iOS system dialogs
    print("\n[nav] Step 1: Dismiss iOS dialogs")
    for _ in range(3):
        if not dismiss_ios_dialogs(driver):
            break
        time.sleep(1)

    screenshot(driver, IMAGES_DIR / "nav" / "01_after_dialogs.png")

    # Step 2: TAP TO START
    print("[nav] Step 2: TAP TO START")
    labels_on_screen = page_source_labels(driver)
    print(f"  Labels on screen: {labels_on_screen[:20]}")

    tapped = (
        try_tap_by_label(driver, "TAP TO START", "Tap to Start", "START") or
        try_tap_by_xpath(driver, '//*[contains(@label, "TAP")]') or
        try_tap_by_xpath(driver, '//*[contains(@label, "START")]')
    )
    if not tapped:
        # Fall back: tap center of lower half (the tap-anywhere area)
        print("  [tap] fallback: tapping center screen")
        tap(driver, w * 0.5, h * 0.75)

    time.sleep(4)
    screenshot(driver, IMAGES_DIR / "nav" / "02_after_start.png")

    # Step 3: Dismiss any post-login dialogs/notifications
    print("[nav] Step 3: Post-login dialogs")
    for _ in range(4):
        labels_on_screen = page_source_labels(driver)
        if any(l in labels_on_screen for l in dismiss_labels_post_login()):
            dismiss_ios_dialogs(driver)
            time.sleep(1.5)
        else:
            break

    screenshot(driver, IMAGES_DIR / "nav" / "03_post_login.png")

    # Step 4: Navigate to Pokemon / My Boxes
    print("[nav] Step 4: Navigate to boxes")
    labels_on_screen = page_source_labels(driver)
    print(f"  Labels on screen: {labels_on_screen[:30]}")

    # Try common navigation labels for HOME boxes
    box_nav_labels = [
        "My Pokémon", "My Pokemon", "Pokémon", "Pokemon",
        "Boxes", "Box", "My Box", "View Pokémon", "See Pokémon",
    ]
    tapped = try_tap_by_label(driver, *box_nav_labels)
    if not tapped:
        # Bottom nav: Pokemon tab is usually leftmost or second from left
        print("  [tap] fallback: tapping bottom-left nav area")
        tap(driver, w * 0.15, h * 0.93)

    time.sleep(3)
    screenshot(driver, IMAGES_DIR / "nav" / "04_after_pokemon_nav.png")

    # Step 5: If we're in a submenu, try to enter boxes
    labels_on_screen = page_source_labels(driver)
    print(f"  Labels on screen: {labels_on_screen[:30]}")

    submenu_labels = ["Boxes", "Box", "My Boxes", "My Box", "VIEW BOXES", "Open Boxes"]
    tapped = try_tap_by_label(driver, *submenu_labels)
    if not tapped:
        try_tap_by_xpath(driver, '//*[contains(@label, "Box")]')
        time.sleep(2)

    time.sleep(3)
    path = screenshot(driver, IMAGES_DIR / "nav" / "05_boxes_reached.png")
    print(f"\n[nav] Navigation complete. Check: {path}")
    return True


def dismiss_labels_post_login() -> list[str]:
    return ["OK", "Close", "Later", "Not Now", "Got it", "Skip", "Allow", "Dismiss", "Continue"]


# ── Phase 2: Box grid capture ─────────────────────────────────────────────────

def capture_all_boxes(driver, start_box: int = 0, total_boxes: int = 50):
    """
    Swipe through all boxes, taking a full-screen screenshot of each.
    Stops when we hit an empty box or reach total_boxes limit.
    """
    w, h = driver.get_window_size()["width"], driver.get_window_size()["height"]

    boxes_done = int(get_state("boxes_captured", "0"))
    if start_box > 0:
        boxes_done = start_box

    print(f"\n[phase2] Capturing box grids starting at box {boxes_done}")

    for box_num in range(boxes_done, total_boxes):
        print(f"\n[phase2] Box {box_num}")
        path = screenshot(driver, IMAGES_DIR / "boxes" / f"box_{box_num:03d}.png")

        # Check if box appears empty (heuristic: very few labels on screen)
        labels = page_source_labels(driver)
        print(f"  Labels: {labels[:15]}")

        import sqlite3
        from collection.schema import get_db
        conn = get_db()
        conn.execute(
            "INSERT INTO boxes(box_number, screenshot_path) VALUES(?,?) ON CONFLICT(box_number) DO UPDATE SET screenshot_path=excluded.screenshot_path",
            (box_num, str(path.relative_to(Path(__file__).parent)))
        )
        conn.commit()
        conn.close()

        set_state("boxes_captured", str(box_num + 1))

        # Swipe left to next box
        swipe_left(driver, w, h)
        time.sleep(2)

    print(f"[phase2] Done. {total_boxes} boxes captured.")


# ── Phase 3: Per-Pokemon detail capture ───────────────────────────────────────

def get_box_slot_coords(driver, slot: int) -> tuple[float, float]:
    """
    Return tap coordinates for a slot (0-29) in the current box.
    Layout: 6 columns x 5 rows. Box grid occupies roughly 10-90% width, 15-85% height.
    Adjust these offsets once you've seen a real box screenshot.
    """
    w, h = driver.get_window_size()["width"], driver.get_window_size()["height"]

    col = slot % COLS_PER_BOX
    row = slot // COLS_PER_BOX

    # Box grid bounds (approximate — tune after seeing actual UI)
    grid_left   = w * 0.05
    grid_right  = w * 0.95
    grid_top    = h * 0.18
    grid_bottom = h * 0.82

    cell_w = (grid_right - grid_left) / COLS_PER_BOX
    cell_h = (grid_bottom - grid_top) / ROWS_PER_BOX

    x = grid_left + cell_w * col + cell_w * 0.5
    y = grid_top  + cell_h * row + cell_h * 0.5
    return x, y


def capture_pokemon_detail(driver, box_num: int, slot: int) -> Path | None:
    """
    Tap a slot, screenshot the detail view, go back.
    Returns the detail screenshot path or None if slot appeared empty.
    """
    w, h = driver.get_window_size()["width"], driver.get_window_size()["height"]
    x, y = get_box_slot_coords(driver, slot)

    labels_before = set(page_source_labels(driver))

    tap(driver, x, y)
    time.sleep(2.5)

    labels_after = set(page_source_labels(driver))
    if labels_after == labels_before:
        # Nothing changed — slot is empty
        return None

    path = screenshot(driver, IMAGES_DIR / "detail" / f"box_{box_num:03d}_slot_{slot:02d}.png")

    # Try to get to the stats/judge view (tap "Check stats" or similar)
    stats_labels = ["Check stats", "Judge", "Stats", "Stats Info", "Check Stats"]
    if try_tap_by_label(driver, *stats_labels):
        time.sleep(2)
        screenshot(driver, IMAGES_DIR / "detail" / f"box_{box_num:03d}_slot_{slot:02d}_stats.png")
        # Go back from stats
        try_tap_by_label(driver, "Back", "back", "Close", "×")
        time.sleep(1.5)

    # Go back to box
    back_tapped = try_tap_by_label(driver, "Back", "back", "Close", "×")
    if not back_tapped:
        driver.back()
    time.sleep(1.5)

    return path


def capture_all_pokemon(driver, start_box: int = 0, start_slot: int = 0):
    """
    For each box, navigate to it and capture every non-empty slot.
    State is saved after each Pokemon so we can resume.
    """
    last_box  = int(get_state("detail_last_box",  str(start_box)))
    last_slot = int(get_state("detail_last_slot", str(start_slot)))
    total_boxes = int(get_state("boxes_captured", "1"))

    print(f"\n[phase3] Capturing Pokemon details. Resuming from box={last_box}, slot={last_slot}")
    print(f"  Total boxes to process: {total_boxes}")

    # Navigate to starting box by swiping
    # (Assumes we're currently on box 0 — you may need to swipe back first)
    w, h = driver.get_window_size()["width"], driver.get_window_size()["height"]
    for _ in range(last_box):
        swipe_left(driver, w, h)
        time.sleep(1.5)

    for box_num in range(last_box, total_boxes):
        print(f"\n[phase3] Box {box_num}")
        slot_start = last_slot if box_num == last_box else 0

        for slot in range(slot_start, SLOTS_PER_BOX):
            print(f"  slot {slot}", end=" ", flush=True)
            path = capture_pokemon_detail(driver, box_num, slot)

            if path:
                print(f"→ captured: {path.name}")
                upsert_pokemon({
                    "box_number": box_num,
                    "box_slot": slot,
                    "detail_screenshot_path": str(path.relative_to(Path(__file__).parent)),
                    "box_screenshot_path": str(
                        (IMAGES_DIR / "boxes" / f"box_{box_num:03d}.png").relative_to(Path(__file__).parent)
                    ),
                })
            else:
                print("→ empty")

            set_state("detail_last_box",  str(box_num))
            set_state("detail_last_slot", str(slot))

        # Go to next box
        if box_num + 1 < total_boxes:
            swipe_left(driver, w, h)
            time.sleep(2)

    set_state("detail_complete", "true")
    print("\n[phase3] All Pokemon detail screenshots captured.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pokemon HOME capture automation")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], default=1,
                        help="1=nav check, 2=box grids, 3=pokemon details")
    parser.add_argument("--boxes", type=int, default=50, help="Max boxes to scan (phase 2)")
    parser.add_argument("--box", type=int, default=0, help="Resume from box N")
    parser.add_argument("--slot", type=int, default=0, help="Resume from slot N")
    args = parser.parse_args()

    init_db()
    print(f"DB: {DB_PATH}")
    print(f"Images: {IMAGES_DIR}")

    print("\nConnecting to iPhone via Appium...")
    driver = create_driver()
    print("Connected.")
    time.sleep(2)

    size = driver.get_window_size()
    print(f"Screen: {size['width']}x{size['height']}")

    try:
        if args.phase == 1:
            print("\n=== Phase 1: Navigation check ===")
            navigate_to_boxes(driver)
            print("\nPhase 1 complete. Review images/nav/ to verify navigation worked.")
            print("If boxes are visible, run phase 2: python capture.py --phase 2")

        elif args.phase == 2:
            print("\n=== Phase 2: Box grid capture ===")
            navigate_to_boxes(driver)
            capture_all_boxes(driver, start_box=args.box, total_boxes=args.boxes)
            print("\nPhase 2 complete. Run phase 3: python capture.py --phase 3")

        elif args.phase == 3:
            print("\n=== Phase 3: Per-Pokemon detail capture ===")
            navigate_to_boxes(driver)
            capture_all_pokemon(driver, start_box=args.box, start_slot=args.slot)
            print("\nPhase 3 complete. Run parse.py to extract metadata.")

    finally:
        driver.quit()
        print("Driver closed.")


if __name__ == "__main__":
    main()
