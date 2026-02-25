#!/usr/bin/env python3
"""
Pokemon HOME Collection Capture
================================
Standalone Appium automation — no LLM in the loop.
Run phases independently; resume at any point via --page / --col / --row.

KEY FINDINGS (from testing):
  - Pokemon HOME is a Unity app — XCUITest accessibility tree is empty.
  - `mobile: tap` does NOT work. Use W3C pointer actions for all in-app taps.
  - iOS system alerts (Software Update, etc.) can still be dismissed via mobile:alert.
  - Navigation: top tabs at y≈0.09 — Trade | Your Room | Pokémon (rightmost, x≈0.85)
  - The "Pokémon" tab shows a flat "All Pokémon" grid (all boxes combined, ~2771 total).

Navigation flow:
  launch screen → TAP TO START → (10s load) → Your Room → tap Pokémon tab → All Pokémon grid

Phases:
  1  Navigate to All Pokémon grid, screenshot it (verify)
  2  Scroll through entire list, screenshot each page
  3  Tap each Pokemon, capture detail screen, go back

Usage:
  python capture.py --phase 1
  python capture.py --phase 2
  python capture.py --phase 3
  python capture.py --phase 3 --page 5 --col 2 --row 1   # resume
  python capture.py --inspect                              # screenshot + page source
"""

import argparse
import hashlib
import re
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from appium import webdriver
from appium.options.ios import XCUITestOptions
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

sys.path.insert(0, str(Path(__file__).parent.parent))
from collection.schema import init_db, upsert_pokemon, get_state, set_state, get_db, IMAGES_DIR, DB_PATH

# ── Device / App ──────────────────────────────────────────────────────────────

DEVICE_UDID = "ae7b05b8416a2adb0c2688a2da14d9fd2aadd7c9"
HOME_BUNDLE = "jp.pokemon.pokemonhome"
APPIUM_URL  = "http://127.0.0.1:4723/wd/hub"
WDA_URL     = "http://127.0.0.1:8100"

# ── Navigation coords (fractions of screen width/height) ─────────────────────

# Top tab bar — confirmed at y≈0.09 via testing
TAB_Y         = 0.09
TAB_POKEMON_X = 0.85   # "Pokémon" tab (rightmost of 3)
TAB_ROOM_X    = 0.50   # "Your Room"
TAB_TRADE_X   = 0.15   # "Trade"

# TAP TO START (launch screen, bottom center)
TAP_TO_START_X = 0.50
TAP_TO_START_Y = 0.83

# ── All Pokémon grid layout ───────────────────────────────────────────────────
# Flat scrollable grid shown on the Pokémon tab.
# Approximately 5 columns. Calibrate GRID_* after phase 1 if needed.

GRID_COLS       = 5
GRID_TOP        = 0.30   # below search/filter bar (empirically: first Pokemon row ~30%)
GRID_BOTTOM     = 0.92   # above bottom safe area
GRID_LEFT       = 0.05
GRID_RIGHT      = 0.95

# ── Timing ────────────────────────────────────────────────────────────────────

WAIT_APP_LOAD   = 12    # after tapping TAP TO START
WAIT_TAP        = 2.0   # after most in-app taps (allow animation)
WAIT_DETAIL     = 2.5   # after tapping a Pokemon (detail view loads)
WAIT_BACK       = 1.5   # after going back
WAIT_SCROLL     = 1.2   # after scroll gesture


# ── Driver ────────────────────────────────────────────────────────────────────

def create_driver() -> webdriver.Remote:
    options = XCUITestOptions()
    options.platform_name = "iOS"
    options.device_name = "iPhone"
    options.udid = DEVICE_UDID
    options.automation_name = "XCUITest"
    options.bundle_id = HOME_BUNDLE
    options.no_reset = True
    options.new_command_timeout = 120
    options.webdriveragent_url = WDA_URL
    return webdriver.Remote(APPIUM_URL, options=options)


# ── Screen helpers ────────────────────────────────────────────────────────────

class Screen:
    def __init__(self, driver):
        size = driver.get_window_size()
        self.w = size["width"]
        self.h = size["height"]

    def pt(self, xf: float, yf: float) -> Tuple[int, int]:
        return int(self.w * xf), int(self.h * yf)

    def slot_pt(self, col: int, row: int) -> Tuple[int, int]:
        """Center point for a grid slot (col 0-4, row 0-N)."""
        cell_w = (GRID_RIGHT - GRID_LEFT) / GRID_COLS
        # Row height approximated equal to cell width (square cells)
        cell_h = cell_w * (self.w / self.h)  # keep aspect
        x = GRID_LEFT + cell_w * col + cell_w * 0.5
        y = GRID_TOP  + cell_h * row + cell_h * 0.5
        return int(self.w * x), int(self.h * y)


# ── Tap / gesture primitives ──────────────────────────────────────────────────
# `mobile: tap` does NOT work for Pokemon HOME (Unity).
# Must use W3C pointer actions.

def tap(driver, x: int, y: int, hold_ms: int = 50):
    finger = PointerInput("touch", "finger1")
    a = ActionBuilder(driver, mouse=finger)
    a.pointer_action.move_to_location(x, y)
    a.pointer_action.pointer_down()
    a.pointer_action.pause(hold_ms / 1000.0)
    a.pointer_action.pointer_up()
    a.perform()


def scroll_down(driver, screen: Screen, distance: float = 0.45):
    """Scroll down by `distance` fraction of screen height."""
    x = screen.w // 2
    y_start = int(screen.h * 0.65)
    y_end   = int(screen.h * (0.65 - distance))
    finger = PointerInput("touch", "finger1")
    a = ActionBuilder(driver, mouse=finger)
    a.pointer_action.move_to_location(x, y_start)
    a.pointer_action.pointer_down()
    a.pointer_action.pause(0.05)
    a.pointer_action.move_to_location(x, y_end)
    a.pointer_action.pause(0.1)
    a.pointer_action.pointer_up()
    a.perform()


def scroll_up_to_top(driver, screen: Screen, steps: int = 20):
    """Scroll back to the top of the list."""
    for _ in range(steps):
        x = screen.w // 2
        y_start = int(screen.h * 0.3)
        y_end   = int(screen.h * 0.7)
        finger = PointerInput("touch", "finger1")
        a = ActionBuilder(driver, mouse=finger)
        a.pointer_action.move_to_location(x, y_start)
        a.pointer_action.pointer_down()
        a.pointer_action.pause(0.02)
        a.pointer_action.move_to_location(x, y_end)
        a.pointer_action.pause(0.05)
        a.pointer_action.pointer_up()
        a.perform()
        time.sleep(0.3)


def ss(driver, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(path))
    print(f"  [ss] {path.relative_to(IMAGES_DIR.parent)}")
    return path


def screenshot_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def page_source(driver) -> str:
    try:
        return driver.page_source
    except Exception:
        return ""


# ── iOS system alert dismissal ────────────────────────────────────────────────
# Native iOS alerts are accessible; use mobile:alert or coordinate taps.

def dismiss_native_alerts(driver, screen: Screen) -> bool:
    src = page_source(driver)

    if "Remind Me Later" in src or "Enter Passcode" in src:
        tap(driver, *screen.pt(0.5, 0.97))
        print("  [alert] tapped Remind Me Later")
        time.sleep(2)
        return True

    for label in ["Later", "Not Now", "Allow", "OK", "Close"]:
        try:
            driver.execute_script("mobile: alert", {"action": "accept", "buttonLabel": label})
            print(f"  [alert] dismissed: '{label}'")
            time.sleep(2)
            return True
        except Exception:
            pass

    return False


def clear_alerts(driver, screen: Screen, max_attempts: int = 5):
    for _ in range(max_attempts):
        if not dismiss_native_alerts(driver, screen):
            break
        time.sleep(0.5)


# ── Navigation ────────────────────────────────────────────────────────────────

WAIT_COLD_START  = 20   # seconds from activate_app → TAP TO START screen appears
WAIT_POST_LOGIN  = 14   # seconds after tapping TAP TO START → Your Room appears


def navigate_to_pokemon_list(driver, screen: Screen):
    """
    Navigate to the 'All Pokémon' flat grid from a cold app start.

    Loading screens are animated (never produce identical screenshots), so we use
    empirically-measured fixed waits rather than screenshot comparison.

    Measured timing (iPhone, Pokemon HOME v3.4.3):
      - Cold start → TAP TO START screen:  ~18s  (using 20s)
      - TAP TO START tap → Your Room:      ~12s  (using 14s)

    Flow:
      1. Terminate → relaunch → wait 20s
      2. Dismiss iOS alerts, tap TAP TO START
      3. Wait 14s for post-login load
      4. Dismiss post-login alerts
      5. Tap Pokémon tab (W3C, x=0.85, y=0.09 confirmed)
    """
    print("[nav] Restarting app...")
    driver.terminate_app(HOME_BUNDLE)
    time.sleep(1)
    driver.activate_app(HOME_BUNDLE)

    print(f"[nav] Waiting {WAIT_COLD_START}s for TAP TO START screen...")
    time.sleep(WAIT_COLD_START)

    clear_alerts(driver, screen)
    ss(driver, IMAGES_DIR / "nav" / "01_launch.png")

    print("[nav] Tapping TAP TO START...")
    tap(driver, *screen.pt(TAP_TO_START_X, TAP_TO_START_Y))

    print(f"[nav] Waiting {WAIT_POST_LOGIN}s for Your Room to load...")
    time.sleep(WAIT_POST_LOGIN)

    clear_alerts(driver, screen)
    ss(driver, IMAGES_DIR / "nav" / "02_your_room.png")

    print("[nav] Tapping Pokémon tab...")
    tap(driver, *screen.pt(TAB_POKEMON_X, TAB_Y))
    time.sleep(WAIT_TAP)
    ss(driver, IMAGES_DIR / "nav" / "03_pokemon_list.png")
    print("[nav] Done — verify 03_pokemon_list.png shows All Pokémon grid")


# ── Phase 2: Capture list pages ───────────────────────────────────────────────

def capture_list_pages(driver, screen: Screen, max_pages: int = 200):
    """
    Scroll through the full 'All Pokémon' list, capturing a screenshot of each
    visible page. Stops when two consecutive pages produce identical screenshots
    (we've hit the bottom).
    """
    print("\n[phase2] Capturing All Pokémon list pages...")

    start_page = int(get_state("pages_captured", "0"))
    if start_page > 0:
        print(f"  Resuming from page {start_page}, scrolling down...")
        for _ in range(start_page):
            scroll_down(driver, screen)
            time.sleep(WAIT_SCROLL)

    prev_hash = None
    page_num = start_page
    for _ in range(max_pages):
        path = ss(driver, IMAGES_DIR / "pages" / f"page_{page_num:04d}.png")
        curr_hash = screenshot_hash(path)

        if curr_hash == prev_hash:
            print(f"  Page {page_num}: same as previous — reached end of list")
            path.unlink()  # delete duplicate
            break

        print(f"  Page {page_num} captured")
        set_state("pages_captured", str(page_num + 1))
        prev_hash = curr_hash
        page_num += 1

        scroll_down(driver, screen)
        time.sleep(WAIT_SCROLL)

    set_state("total_pages", str(page_num))
    print(f"[phase2] Done. {page_num} pages captured.")


# ── Phase 3: Per-Pokemon detail capture ───────────────────────────────────────

def visible_rows(screen: Screen) -> int:
    """How many full grid rows are visible in the current viewport."""
    grid_h = (GRID_BOTTOM - GRID_TOP) * screen.h
    cell_w = (GRID_RIGHT - GRID_LEFT) * screen.w / GRID_COLS
    cell_h = cell_w  # square cells
    return max(1, int(grid_h / cell_h))


def capture_slot(driver, screen: Screen, position: int, col: int, row: int) -> Optional[Path]:
    """
    Tap a grid slot, screenshot the detail view, go back.
    position = global sequential index for file naming.
    Returns detail screenshot path or None if slot was empty.

    Uses screenshot comparison (not page_source) — Unity keeps page_source constant.
    """
    x, y = screen.slot_pt(col, row)

    # Snapshot before tap (list state reference for empty slot detection)
    before = IMAGES_DIR / "detail" / "_before.png"
    ss(driver, before)
    hash_before = screenshot_hash(before)

    tap(driver, x, y)
    time.sleep(WAIT_DETAIL)

    # Snapshot after tap
    after = IMAGES_DIR / "detail" / "_after.png"
    ss(driver, after)
    hash_after = screenshot_hash(after)

    if hash_after == hash_before:
        # Screen didn't change — empty slot
        return None

    # We're on a detail screen — save it
    path = IMAGES_DIR / "detail" / f"pokemon_{position:04d}_c{col}r{row}.png"
    after.rename(path)
    print(f"  [ss] detail/{path.name}")

    # Close detail view via the × button (green circle, center-bottom of detail screen)
    # Measured from screenshot: button center at y=2207/2436 (90.6% down, 3x retina image)
    tap(driver, *screen.pt(0.50, 0.906))
    time.sleep(WAIT_BACK)

    before.unlink(missing_ok=True)
    return path


def capture_all_pokemon(driver, screen: Screen,
                         start_page: int = 0,
                         start_col: int = 0,
                         start_row: int = 0,
                         limit: Optional[int] = None):
    """
    Walk the entire All Pokémon list, tapping each slot for its detail screen.
    Scrolls down one page at a time, capturing every visible slot before scrolling.
    State is persisted after every slot for resumability.
    """
    rows_per_page = visible_rows(screen)
    print(f"\n[phase3] rows_per_page={rows_per_page}, cols={GRID_COLS}")
    print(f"  Resuming from page={start_page} col={start_col} row={start_row}")

    # Scroll to starting page
    if start_page > 0:
        print(f"  Scrolling to page {start_page}...")
        for _ in range(start_page):
            scroll_down(driver, screen)
            time.sleep(WAIT_SCROLL)

    total_pages = int(get_state("total_pages", "200"))
    position = start_page * rows_per_page * GRID_COLS

    prev_page_hash = None

    for page_num in range(start_page, total_pages):
        print(f"\n[phase3] Page {page_num}")

        # Detect end-of-list (same screenshot as previous page)
        tmp = IMAGES_DIR / "detail" / "_tmp_page.png"
        ss(driver, tmp)
        curr_hash = screenshot_hash(tmp)
        if curr_hash == prev_page_hash:
            print("  End of list detected.")
            tmp.unlink()
            break
        prev_page_hash = curr_hash
        tmp.unlink()

        row_start = start_row if page_num == start_page else 0
        col_start = start_col if page_num == start_page else 0

        for row in range(row_start, rows_per_page):
            c_start = col_start if row == row_start else 0
            for col in range(c_start, GRID_COLS):
                print(f"  p{page_num} r{row} c{col} ", end="", flush=True)
                path = capture_slot(driver, screen, position, col, row)

                if path:
                    print(f"→ {path.name}")
                    upsert_pokemon({
                        "box_number": page_num,   # repurposed: page = rough box equivalent
                        "box_slot":   row * GRID_COLS + col,
                        "detail_screenshot_path": str(path.relative_to(Path(__file__).parent)),
                    })
                else:
                    print("→ empty/end")

                set_state("detail_last_page", str(page_num))
                set_state("detail_last_col",  str(col))
                set_state("detail_last_row",  str(row))
                position += 1

                if limit and position >= limit:
                    print(f"\n[phase3] Reached limit of {limit}. Stopping.")
                    return

        scroll_down(driver, screen)
        time.sleep(WAIT_SCROLL)

    set_state("detail_complete", "true")
    print("\n[phase3] Complete. Run: python parse.py")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pokemon HOME capture")
    parser.add_argument("--phase",   type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--page",    type=int, default=0,   help="Resume from page N")
    parser.add_argument("--col",     type=int, default=0,   help="Resume from col N")
    parser.add_argument("--row",     type=int, default=0,   help="Resume from row N")
    parser.add_argument("--limit",   type=int, default=None, help="Max pages to capture (phase 2)")
    parser.add_argument("--inspect", action="store_true",
                        help="Screenshot + page source dump, then exit")
    args = parser.parse_args()

    init_db()
    print(f"DB:     {DB_PATH}")
    print(f"Images: {IMAGES_DIR}\n")

    print("Connecting to Appium...")
    driver = create_driver()
    screen = Screen(driver)
    print(f"Connected. Screen: {screen.w}x{screen.h}")
    time.sleep(1)

    try:
        if args.inspect:
            out = ss(driver, IMAGES_DIR / "nav" / "inspect.png")
            src = page_source(driver)
            labels = re.findall(r'label="([^"]+)"', src)
            print(f"Labels: {labels[:30]}")
            print(f"Source: {len(src)} chars")
            (IMAGES_DIR / "nav" / "inspect_source.xml").write_text(src)
            return

        if args.phase == 1:
            print("=== Phase 1: Navigation check ===")
            navigate_to_pokemon_list(driver, screen)
            print("\nCheck images/nav/03_pokemon_list.png")
            print("If All Pokémon grid is visible, run phase 2:")
            print("  python capture.py --phase 2")

        elif args.phase == 2:
            print("=== Phase 2: List page capture ===")
            navigate_to_pokemon_list(driver, screen)
            capture_list_pages(driver, screen, max_pages=args.limit or 200)
            print("\nRun phase 3:")
            print("  python capture.py --phase 3")

        elif args.phase == 3:
            print("=== Phase 3: Pokemon detail capture ===")
            navigate_to_pokemon_list(driver, screen)
            capture_all_pokemon(driver, screen,
                                 start_page=args.page,
                                 start_col=args.col,
                                 start_row=args.row,
                                 limit=args.limit)

    finally:
        driver.quit()
        print("Driver closed.")


if __name__ == "__main__":
    main()
