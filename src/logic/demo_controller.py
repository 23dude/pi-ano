# src/logic/demo_controller.py

from __future__ import annotations

import random
from typing import Callable, Optional


class DemoController:
    """
    Demo mode state machine.

    Cycles: PIANO (20s) → RHYTHM_SELECT (wait for user / 20s timeout)
            → RHYTHM_PLAY (until postgame done) → SONG (until finished) → PIANO …
    """

    MENU_DURATION: float = 5.0
    PIANO_DURATION: float = 15.0
    RHYTHM_SELECT_TIMEOUT: float = 15.0

    def __init__(
        self,
        switch_mode: Callable[[str, float], None],
        rhythm,
        song,
        led=None,
    ) -> None:
        self._switch_mode = switch_mode
        self._rhythm = rhythm
        self._song = song
        self._led = led

        self.active: bool = False
        self._phase: str = ""
        self._phase_start: float = 0.0
        self._postgame_just_finished: bool = False

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def postgame_just_finished(self) -> bool:
        return self._postgame_just_finished

    @postgame_just_finished.setter
    def postgame_just_finished(self, value: bool) -> None:
        self._postgame_just_finished = value

    # ------------------------------------------------------------------
    # Enter / Exit
    # ------------------------------------------------------------------

    def enter(self, now: float) -> None:
        print("[DEMO] Entering demo mode")
        self.active = True
        self._start_piano(now)

    def exit(self, now: float) -> None:
        print("[DEMO] Exiting demo mode")
        self.active = False
        self._phase = ""
        self._song.loop_playlist = True
        self._switch_mode("menu", now)

    # ------------------------------------------------------------------
    # Phase starters
    # ------------------------------------------------------------------

    def _start_menu(self, now: float) -> None:
        self._phase = "MENU"
        self._phase_start = now
        self._switch_mode("menu", now)
        print("[DEMO] Phase: MENU (5s)")

    def _start_piano(self, now: float) -> None:
        self._phase = "PIANO"
        self._phase_start = now
        self._switch_mode("piano", now)
        print("[DEMO] Phase: PIANO (20s)")

    def _start_rhythm(self, now: float) -> None:
        self._phase = "RHYTHM_SELECT"
        self._phase_start = now
        self._switch_mode("rhythm", now)
        print("[DEMO] Phase: RHYTHM_SELECT (waiting for difficulty, 20s timeout)")

    def _start_song(self, now: float) -> None:
        self._phase = "SONG"
        self._phase_start = now
        self._song.loop_playlist = False
        self._switch_mode("song", now)

        # Find PeppaPig.mid in playlist, fallback to random
        target_index = None
        for i, p in enumerate(self._song.playlist):
            if "PeppaPig" in p.name:
                target_index = i
                break

        if target_index is None:
            target_index = random.randint(0, len(self._song.playlist) - 1)
            print(f"[DEMO] Phase: SONG (PeppaPig not found, random index={target_index})")
        else:
            print(f"[DEMO] Phase: SONG (PeppaPig, index={target_index})")

        self._song._start_song_by_index(target_index, now)

    # ------------------------------------------------------------------
    # Manual skip (long-press D14 during demo)
    # ------------------------------------------------------------------

    def cycle_next(self, now: float) -> None:
        if self._phase == "PIANO":
            self._start_rhythm(now)
        elif self._phase in ("RHYTHM_SELECT", "RHYTHM_PLAY"):
            self._start_song(now)
        elif self._phase == "SONG":
            self._start_piano(now)
        print(f"[DEMO] Manual skip → {self._phase}")

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, now: float) -> None:
        if not self.active:
            return

        if self._phase == "MENU":
            if now - self._phase_start >= self.MENU_DURATION:
                self._start_piano(now)

        elif self._phase == "PIANO":
            if now - self._phase_start >= self.PIANO_DURATION:
                self._start_rhythm(now)

        elif self._phase == "RHYTHM_SELECT":
            if getattr(self._rhythm, "phase", None) == "PLAY":
                self._phase = "RHYTHM_PLAY"
                print("[DEMO] Phase: RHYTHM_PLAY (user selected difficulty)")
            elif now - self._phase_start >= self.RHYTHM_SELECT_TIMEOUT:
                print("[DEMO] RHYTHM_SELECT timeout, skipping to SONG")
                self._start_song(now)

        elif self._phase == "RHYTHM_PLAY":
            if self._postgame_just_finished:
                self._postgame_just_finished = False
                self._start_song(now)

        elif self._phase == "SONG":
            if self._song.song_finished:
                self._start_piano(now)

    # ------------------------------------------------------------------
    # LED indicator
    # ------------------------------------------------------------------

    def draw_normal_indicator(self) -> None:
        """Purple pixel at top-right corner when NOT in demo mode."""
        if self._led is None:
            return
        self._led.set_xy(31, 0, (128, 0, 128))
        # show() is called centrally by InputManager
