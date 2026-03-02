import time
import random
from loguru import logger


class RateLimiter:
    """
    Ограничитель частоты запросов.

    Рекомендуемые интервалы для ЦИАН:
    - Между страницами: 5–15 сек (рандом)
    - Между действиями на странице: 1–3 сек
    - Длинная пауза каждые 8–12 страниц: 30–60 сек
    - После ошибки/CAPTCHA: 60–180 сек
    """

    def __init__(
        self,
        page_delay: tuple[float, float] = (5.0, 15.0),
        action_delay: tuple[float, float] = (1.0, 3.0),
        long_pause_every: tuple[int, int] = (8, 12),
        long_pause_range: tuple[float, float] = (30.0, 60.0),
        error_pause_range: tuple[float, float] = (60.0, 180.0),
        section_pause_range: tuple[float, float] = (20.0, 40.0),
    ):
        self.page_delay = page_delay
        self.action_delay = action_delay
        self.long_pause_every = long_pause_every
        self.long_pause_range = long_pause_range
        self.error_pause_range = error_pause_range
        self.section_pause_range = section_pause_range

        self._request_count = 0
        self._next_long_pause_at = random.randint(*long_pause_every)

    def wait_between_pages(self) -> None:
        """Пауза между переходами по страницам (5–15 сек)."""
        self._request_count += 1

        if self._request_count >= self._next_long_pause_at:
            self._long_pause()
            self._next_long_pause_at = (
                self._request_count + random.randint(*self.long_pause_every)
            )
            return

        delay = random.uniform(*self.page_delay)
        logger.debug(f"⏳ Пауза между страницами: {delay:.1f} сек")
        time.sleep(delay)

    def wait_between_actions(self) -> None:
        """Пауза между действиями на странице (1–3 сек)."""
        delay = random.uniform(*self.action_delay)
        time.sleep(delay)

    def wait_before_detail(self) -> None:
        """Пауза перед переходом на детальную страницу."""
        delay = random.uniform(
            self.page_delay[0] * 0.8,
            self.page_delay[1] * 1.2,
        )
        logger.debug(f"⏳ Пауза перед деталями: {delay:.1f} сек")
        time.sleep(delay)

    def _long_pause(self) -> None:
        """Длинная пауза (имитация: человек отвлёкся)."""
        delay = random.uniform(*self.long_pause_range)
        logger.info(
            f"☕ Длинная пауза ({self._request_count} запросов): "
            f"{delay:.1f} сек"
        )
        time.sleep(delay)

    def wait_on_error(self) -> None:
        """Увеличенная пауза после ошибки (60–180 сек)."""
        delay = random.uniform(*self.error_pause_range)
        logger.warning(f"⚠️ Пауза после ошибки: {delay:.1f} сек")
        time.sleep(delay)

    def wait_on_captcha(self) -> None:
        """Пауза после CAPTCHA (120–300 сек)."""
        delay = random.uniform(120.0, 300.0)
        logger.warning(f"🔒 Пауза после CAPTCHA: {delay:.1f} сек")
        time.sleep(delay)

    def wait_between_sections(self) -> None:
        """Пауза между разделами (типами комнатности)."""
        delay = random.uniform(*self.section_pause_range)
        logger.info(f"📋 Пауза между разделами: {delay:.1f} сек")
        time.sleep(delay)

    @property
    def total_requests(self) -> int:
        return self._request_count