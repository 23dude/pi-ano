# src/logic/rhythm_postgame.py

from __future__ import annotations

from typing import Optional

from src.hardware.pico.pico_mode_display import PicoModeDisplay
from src.logic.high_scores import HighScoreStore


class RhythmPostgameController:
    """
    Orchestrates the post-game score display timeline on the Pico screen
    after a rhythm round finishes (phase == "DONE").

    Stages: result_scroll → user_label → user_score → best_label
            → best_score_wait_done → pi_colors_during_title
    """

    # Timing for each stage (seconds)
    RESULT_SCROLL_SEC: float = 4.0
    USER_LABEL_SEC: float = 3.0
    USER_SCORE_SEC: float = 3.0
    BEST_LABEL_SEC: float = 1.0
    PI_COLORS_DURING_TITLE_SEC: float = 3.0

    def __init__(
        self,
        rhythm,
        pico_display: Optional[PicoModeDisplay] = None,
    ) -> None:
        self._rhythm = rhythm
        self._pico_display = pico_display
        self._high_scores = HighScoreStore()

        self.started: bool = False
        self.stage: Optional[str] = None
        self._t0: float = 0.0
        self.pico_best_score_done: bool = False

        self._last_score: int = 0
        self._last_best: int = 0
        self._last_max_score: int = 0
        self._last_difficulty: str = "easy"

        self.just_finished: bool = False

    def is_in_postgame(self) -> bool:
        return bool(self.started and self.stage is not None)

    def reset_state(self) -> None:
        self.started = False
        self.stage = None
        self.pico_best_score_done = False

    def render_difficulty_colors(self) -> None:
        if hasattr(self._rhythm, "show_mode_colors"):
            try:
                self._rhythm.show_mode_colors()
                return
            except Exception as e:
                print("[RhythmPostgame] rhythm.show_mode_colors error:", e)

        if hasattr(self._rhythm, "_render_wait_countdown"):
            try:
                self._rhythm._render_wait_countdown()
                return
            except Exception as e:
                print("[RhythmPostgame] rhythm._render_wait_countdown error:", e)

    def run_timeline(self, now: float, demo_active: bool = False) -> None:
        phase = getattr(self._rhythm, "phase", None)

        if phase != "DONE":
            self.started = False
            self.stage = None
            self.pico_best_score_done = False
            return

        if self._pico_display is None:
            return

        if not self.started:
            self._begin_postgame(now)
            return

        elapsed = now - self._t0

        if self.stage == "result_scroll":
            if elapsed >= self.RESULT_SCROLL_SEC:
                self._send(self._pico_display.send_rhythm_user_score_label)
                self.stage = "user_label"
                self._t0 = now

        elif self.stage == "user_label":
            if elapsed >= self.USER_LABEL_SEC:
                max_s = self._last_max_score
                text = f"{self._last_score}/{max_s}" if max_s > 0 else str(self._last_score)
                self._send(self._pico_display.send_rhythm_user_score, text)
                self.stage = "user_score"
                self._t0 = now

        elif self.stage == "user_score":
            if elapsed >= self.USER_SCORE_SEC:
                self._send(self._pico_display.send_rhythm_best_score_label)
                self.stage = "best_label"
                self._t0 = now

        elif self.stage == "best_label":
            if elapsed >= self.BEST_LABEL_SEC:
                max_s = self._last_max_score
                text = f"{self._last_best}/{max_s}" if max_s > 0 else str(self._last_best)
                self._send(self._pico_display.send_rhythm_best_score, text)
                self.stage = "best_score_wait_done"
                self._t0 = now

        elif self.stage == "best_score_wait_done":
            if self.pico_best_score_done:
                if demo_active:
                    self._finish_postgame()
                    return

                self._send(self._pico_display.send_rhythm_back_to_title)
                self.stage = "pi_colors_during_title"
                self._t0 = now

        elif self.stage == "pi_colors_during_title":
            if elapsed >= self.PI_COLORS_DURING_TITLE_SEC:
                try:
                    self._rhythm.reset(now)
                except Exception as e:
                    print("[RhythmPostgame] rhythm.reset error:", e)
                self._finish_postgame()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _begin_postgame(self, now: float) -> None:
        self.started = True
        self.stage = "result_scroll"
        self._t0 = now
        self.pico_best_score_done = False

        score = getattr(self._rhythm, "score", 0)
        max_score = getattr(self._rhythm, "max_score", 0)
        difficulty = getattr(self._rhythm, "difficulty", "easy")

        self._last_score = score
        self._last_max_score = max_score
        self._last_difficulty = difficulty

        best_before = self._high_scores.get_best(difficulty)
        is_new_record = self._high_scores.update_if_better(difficulty, score)
        best_after = max(best_before, score)
        self._last_best = best_after

        print(
            f"[RhythmPostgame] Rhythm DONE: {score}/{max_score}, "
            f"best={best_before}→{best_after}, diff={difficulty}, "
            f"new_record={is_new_record}"
        )

        if is_new_record:
            self._send(self._pico_display.send_rhythm_challenge_success)
        else:
            self._send(self._pico_display.send_rhythm_challenge_fail)

    def _finish_postgame(self) -> None:
        self.started = False
        self.stage = None
        self.pico_best_score_done = False
        self.just_finished = True

    def _send(self, method, *args) -> None:
        try:
            method(*args)
        except Exception as e:
            print(f"[RhythmPostgame] {method.__name__} error: {e}")
