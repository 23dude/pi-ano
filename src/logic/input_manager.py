# src/logic/input_manager.py

from __future__ import annotations

from typing import List, Optional

from src.logic.input_event import InputEvent, EventType
from src.hardware.config.keys import KeyId
from src.hardware.pico.pico_mode_display import PicoModeDisplay
from src.logic.demo_controller import DemoController
from src.logic.rhythm_postgame import RhythmPostgameController


class InputManager:
    def __init__(
        self,
        menu,
        piano,
        rhythm,
        song,
        pico_display: Optional[PicoModeDisplay] = None,
        led=None,
    ) -> None:
        self.menu = menu
        self.piano = piano
        self.rhythm = rhythm
        self.song = song

        self.pico_display = pico_display
        self._led = led

        self.current_mode: str = "menu"
        self._mode_order = ["menu", "piano", "rhythm", "song"]

        self._postgame = RhythmPostgameController(rhythm, pico_display)
        self._demo = DemoController(self._switch_mode, rhythm, song, led)

    @property
    def current_mode_name(self) -> str:
        return self.current_mode

    # Kept for backwards compat with main.py references
    @property
    def _demo_active(self) -> bool:
        return self._demo.active

    def _get_audio_engine(self):
        for mode in (self.piano, self.rhythm, self.song):
            audio = getattr(mode, "audio", None)
            if audio is not None:
                return audio
        return None

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _cycle_mode(self, now: float) -> None:
        if self.current_mode not in self._mode_order:
            next_mode = "menu"
        else:
            idx = self._mode_order.index(self.current_mode)
            next_mode = self._mode_order[(idx + 1) % len(self._mode_order)]
        self._switch_mode(next_mode, now)

    def _switch_mode(self, mode_name: str, now: float) -> None:
        if mode_name == self.current_mode:
            return

        if self.current_mode == "rhythm":
            self.rhythm.on_exit()
            self._postgame.reset_state()

        self.current_mode = mode_name
        print(f"[MODE] Switched to: {self.current_mode.upper()}")

        if mode_name == "menu":
            self.menu.reset(now)

        elif mode_name == "piano":
            if hasattr(self.piano, "randomize_palette"):
                self.piano.randomize_palette()
            self.piano.reset(now)

        elif mode_name == "rhythm":
            self._postgame.reset_state()
            self.rhythm.reset(now)

        elif mode_name == "song":
            self.song.reset(now)

        if self.pico_display is not None:
            try:
                self.pico_display.show_mode(mode_name)
            except Exception as e:
                print("[InputManager] pico_display.show_mode error:", e)

    # ------------------------------------------------------------------
    # Pico serial messages
    # ------------------------------------------------------------------

    def _handle_pico_message(self, msg: str, now: float) -> None:
        if not msg:
            return
        text = msg.strip()
        if not text:
            return

        up = text.upper()

        if up.startswith("RHYTHM:COUNTDOWN_DONE"):
            if self.current_mode == "rhythm":
                print("[InputManager] Pico → RHYTHM:COUNTDOWN_DONE")
                try:
                    self.rhythm.start_play_after_countdown(now)
                except Exception as e:
                    print("[InputManager] rhythm.start_play_after_countdown error:", e)
            return

        if up.startswith("RHYTHM:BEST_SCORE_DONE"):
            if self.current_mode == "rhythm":
                print("[InputManager] Pico → RHYTHM:BEST_SCORE_DONE")
                self._postgame.pico_best_score_done = True
            return

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def handle_events(self, events: List[InputEvent], now: float) -> None:
        for ev in events:
            if ev.type == EventType.DEMO_TOGGLE:
                if self._demo.active:
                    self._demo.exit(now)
                else:
                    self._demo.enter(now)
                return

            if ev.type == EventType.NEXT_SF2:
                audio = self._get_audio_engine()
                if audio is not None:
                    try:
                        audio.cycle_soundfont()
                    except Exception as e:
                        print("[InputManager] audio.cycle_soundfont error:", e)
                continue

            if ev.type == EventType.MODE_SWITCH and ev.mode_name:
                if self._demo.active:
                    continue
                self._switch_mode(ev.mode_name, now)
                continue

            if ev.type == EventType.NEXT_MODE:
                if self._demo.active:
                    self._demo.cycle_next(now)
                    continue
                self._cycle_mode(now)
                continue

            if (
                self.current_mode == "song"
                and ev.type == EventType.NOTE_ON
                and ev.key == KeyId.KEY_3
                and getattr(ev, "source", None) == "button"
            ):
                try:
                    self.song.skip_to_next(now)
                except Exception as e:
                    print("[InputManager] song.skip_to_next error:", e)
                continue

        self._dispatch_mode_events(events, now)

    def _dispatch_mode_events(self, events: List[InputEvent], now: float) -> None:
        if self.current_mode == "menu":
            self.menu.handle_events(events)

        elif self.current_mode == "piano":
            filtered: List[InputEvent] = []
            for ev in events:
                if ev.type in (EventType.NOTE_ON, EventType.NOTE_OFF):
                    if getattr(ev, "source", None) == "button":
                        continue
                filtered.append(ev)
            self.piano.handle_events(filtered)

        elif self.current_mode == "rhythm":
            if self._postgame.is_in_postgame():
                return
            self._handle_rhythm_events(events, now)

        elif self.current_mode == "song":
            self.song.handle_events(events)

    def _handle_rhythm_events(self, events: List[InputEvent], now: float) -> None:
        phase = getattr(self.rhythm, "phase", None)

        if phase == "WAIT_COUNTDOWN":
            for ev in events:
                if ev.type != EventType.NOTE_ON:
                    continue
                if getattr(ev, "source", None) != "button":
                    continue
                if ev.key is None:
                    continue

                difficulty: Optional[str] = None
                if ev.key == KeyId.KEY_3:
                    difficulty = "easy"
                elif ev.key == KeyId.KEY_2:
                    difficulty = "medium"
                elif ev.key == KeyId.KEY_1:
                    difficulty = "hard"

                if difficulty is None:
                    continue

                try:
                    self.rhythm.set_difficulty(difficulty)
                except Exception as e:
                    print(f"[InputManager] rhythm.set_difficulty('{difficulty}') error:", e)

                print(f"[InputManager] Rhythm difficulty selected: {difficulty}")

                if self.pico_display is not None:
                    try:
                        self.pico_display.send_rhythm_level(difficulty)
                    except Exception as e:
                        print("[InputManager] pico_display.send_rhythm_level error:", e)

                return
            return

        if phase == "PLAY":
            button_events: List[InputEvent] = [
                ev
                for ev in events
                if getattr(ev, "source", None) == "button"
                and ev.type in (EventType.NOTE_ON, EventType.NOTE_OFF)
            ]
            if button_events:
                self.rhythm.handle_events(button_events)
            return

    # ------------------------------------------------------------------
    # Main update loop
    # ------------------------------------------------------------------

    def update(self, now: float) -> None:
        # 0) Demo mode transitions
        self._demo.update(now)

        # 1) Poll Pico messages
        if self.pico_display is not None:
            try:
                messages = self.pico_display.poll_messages()
            except Exception as e:
                print("[InputManager] pico_display.poll_messages error:", e)
                messages = []
            for msg in messages:
                self._handle_pico_message(msg, now)

        # 2) Mode updates
        if self.current_mode == "menu":
            self.menu.update(now)

        elif self.current_mode == "piano":
            self.piano.update(now)

        elif self.current_mode == "rhythm":
            phase = getattr(self.rhythm, "phase", None)
            in_postgame = (phase == "DONE" and self._postgame.is_in_postgame())
            if not in_postgame:
                self.rhythm.update(now)

            self._postgame.run_timeline(now, demo_active=self._demo.active)

            if self._postgame.just_finished and self._demo.active:
                self._demo.postgame_just_finished = True
                self._postgame.just_finished = False

            if self._postgame.stage == "pi_colors_during_title":
                self._postgame.render_difficulty_colors()

        elif self.current_mode == "song":
            self.song.update(now)

        # 3) Normal mode indicator: purple pixel at top-right corner
        if not self._demo.active:
            self._demo.draw_normal_indicator()

        # 4) Single LED show() per frame
        if self._led is not None:
            self._led.show()
