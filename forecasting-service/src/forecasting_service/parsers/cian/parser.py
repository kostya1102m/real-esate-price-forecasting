import time
import random
from typing import Optional
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

from forecasting_service.parsers.common.browser import (
    BrowserManager,
    CaptchaDetectedError,
)
from forecasting_service.parsers.common.rate_limiter import RateLimiter
from forecasting_service.parsers.cian.constants import (
    BASE_LISTING_URL,
    REGIONS,
    ROOM_PARAMS,
    LISTING_CARD_SELECTOR,
)
from forecasting_service.parsers.cian.page_parser import (
    parse_listing_page,
    parse_detail_page,
    is_empty_listing,
)
from forecasting_service.parsers.cian.models import CianFlat


DATASETS_DIR = Path(__file__).resolve().parent.parent.parent / "datasets"


class CianParser:
    """
    Парсер объявлений ЦИАН.

    Стратегия обхода блокировок:
    1. Selenium + selenium-stealth (реальный Chrome)
    2. Рандомизированные задержки 5–15 сек
    3. Эмуляция скролла (имитация чтения)
    4. Ротация User-Agent каждые 10 страниц
    5. Автоматический рестарт при CAPTCHA
    6. Промежуточное сохранение данных
    """

    def __init__(
        self,
        location: str = "Владивосток",
        headless: bool = True,
        page_delay: tuple[float, float] = (5.0, 15.0),
        action_delay: tuple[float, float] = (1.0, 3.0),
        max_retries: int = 3,
        collect_extra_data: bool = True,
        rotate_ua_every: int = 10,
    ):
        if location not in REGIONS:
            raise ValueError(
                f"Неизвестный город: {location}. "
                f"Доступные: {list(REGIONS.keys())}"
            )

        self.location = location
        self.region_id = REGIONS[location]
        self.max_retries = max_retries
        self.collect_extra_data = collect_extra_data

        self.browser = BrowserManager(
            headless=headless,
            rotate_ua_every=rotate_ua_every,
        )

        self.rate_limiter = RateLimiter(
            page_delay=page_delay,
            action_delay=action_delay,
        )

        self._captcha_count = 0
        self._max_captcha = 5

    def _build_listing_url(
        self, rooms: int | str, page: int = 1
    ) -> str:
        """Строит URL страницы листинга."""
        room_param = ROOM_PARAMS.get(rooms, "")
        params = [
            "engine_version=2",
            f"p={page}",
            "with_neighbors=0",
            f"region={self.region_id}",
            "deal_type=sale",
            "offer_type=flat",
            room_param,
            "only_flat=1",
        ]
        return (
            f"{BASE_LISTING_URL}"
            f"?{'&'.join(p for p in params if p)}"
        )

    def _handle_captcha(self) -> bool:
        """
        Обработка CAPTCHA.

        Returns:
            True если можно продолжать, False если лимит исчерпан
        """
        self._captcha_count += 1
        logger.warning(
            f"🔒 CAPTCHA #{self._captcha_count}"
            f"/{self._max_captcha}"
        )

        if self._captcha_count >= self._max_captcha:
            logger.error(
                "Достигнут лимит CAPTCHA. "
                "Останавливаем парсинг."
            )
            return False

        # Перезапуск браузера + длинная пауза
        logger.info("🔄 Перезапуск браузера...")
        self.browser.stop()
        self.rate_limiter.wait_on_captcha()
        self.browser.restart_with_new_ua()

        return True

    def _save_intermediate(
        self, flats: list[CianFlat], label: str
    ) -> None:
        """Промежуточное сохранение данных."""
        if not flats:
            return

        DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = (
            DATASETS_DIR
            / f"intermediate_{label}_{timestamp}.csv"
        )

        df = pd.DataFrame(
            [flat.model_dump() for flat in flats]
        )
        df.to_csv(filepath, index=False, sep=";", encoding="utf-8")
        logger.info(
            f"💾 Промежуточное сохранение: "
            f"{filepath.name} ({len(flats)} записей)"
        )

    def collect_page(
        self, rooms: int | str, page: int
    ) -> list[CianFlat]:
        """Собирает объявления с одной страницы листинга."""
        url = self._build_listing_url(rooms=rooms, page=page)

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"📄 Страница {page} | rooms={rooms} | "
                    f"попытка {attempt}/{self.max_retries}"
                )

                # Загрузка с Explicit Wait + скролл
                html = self.browser.get_page(
                    url,
                    wait_selector=LISTING_CARD_SELECTOR,
                    wait_timeout=15,
                    scroll=True,
                )

                # Эмуляция движений мыши (иногда)
                if random.random() < 0.4:
                    self.browser.simulate_mouse_movement(
                        self.browser.driver
                    )

                # Проверка пустого листинга
                if is_empty_listing(html):
                    logger.info(
                        f"📭 Страница {page} пуста — "
                        f"объявления закончились"
                    )
                    return []

                # Парсинг
                flats = parse_listing_page(html)

                if not flats:
                    logger.warning(
                        f"⚠️ Не извлечено объявлений "
                        f"со страницы {page}"
                    )
                    if attempt < self.max_retries:
                        self.rate_limiter.wait_on_error()
                        continue
                    return []

                logger.info(
                    f"✅ Страница {page}: "
                    f"{len(flats)} объявлений"
                )
                return flats

            except CaptchaDetectedError:
                can_continue = self._handle_captcha()
                if not can_continue:
                    raise
                # Повторяем попытку после рестарта

            except TimeoutError:
                logger.warning(
                    f"⏰ Таймаут страницы {page}"
                )
                if attempt < self.max_retries:
                    self.rate_limiter.wait_on_error()
                    self.browser.restart_with_new_ua()

            except Exception as e:
                logger.error(
                    f"❌ Ошибка на странице {page}: {e}"
                )
                if attempt < self.max_retries:
                    self.rate_limiter.wait_on_error()
                else:
                    return []

        return []

    def _enrich_with_details(
        self, flats: list[CianFlat]
    ) -> list[CianFlat]:
        """
        Обогащает данные с детальных страниц.
        Переходит на каждое объявление для сбора доп. полей.
        """
        if not self.collect_extra_data:
            return flats

        logger.info(
            f"📋 Сбор доп. данных: {len(flats)} объявлений"
        )

        enriched_count = 0

        for i, flat in enumerate(flats):
            if not flat.url:
                continue

            try:
                logger.debug(
                    f"  [{i + 1}/{len(flats)}] "
                    f"{flat.url[:60]}..."
                )

                # Пауза перед переходом на детальную страницу
                self.rate_limiter.wait_before_detail()

                html = self.browser.get_page(
                    flat.url,
                    scroll=True,
                )
                details = parse_detail_page(html)

                # Обновляем только пустые поля
                updated = False
                for field_name in [
                    "living_meters",
                    "kitchen_meters",
                    "year_of_construction",
                    "house_material_type",
                    "finish_type",
                    "heating_type",
                ]:
                    new_val = details.get(field_name)
                    current_val = getattr(flat, field_name, None)
                    if new_val and not current_val:
                        setattr(flat, field_name, new_val)
                        updated = True

                if updated:
                    enriched_count += 1

            except CaptchaDetectedError:
                logger.warning(
                    "🔒 CAPTCHA при сборе деталей — "
                    "пропускаем остальные"
                )
                break

            except Exception as e:
                logger.debug(f"  Ошибка деталей: {e}")

        logger.info(
            f"📋 Обогащено: {enriched_count}/{len(flats)}"
        )
        return flats

    def collect(
        self,
        rooms: int | str | tuple = (1, 2, 3),
        start_page: int = 1,
        end_page: int = 5,
        with_extra_data: bool = True,
    ) -> pd.DataFrame:
        """
        Основной метод сбора данных.

        Args:
            rooms: тип(ы) комнатности
            start_page: начальная страница
            end_page: конечная страница
            with_extra_data: собирать ли доп. данные

        Returns:
            pd.DataFrame с данными объявлений
        """
        if isinstance(rooms, (int, str)):
            rooms = (rooms,)

        self.collect_extra_data = with_extra_data
        all_flats: list[CianFlat] = []

        try:
            self.browser.start()

            for room_idx, room_type in enumerate(rooms):
                logger.info(f"\n{'═' * 50}")
                logger.info(f"🏠 Комнатность: {room_type}")
                logger.info(f"{'═' * 50}")

                consecutive_empty = 0
                room_flats: list[CianFlat] = []

                for page in range(start_page, end_page + 1):
                    # Пауза между страницами
                    if page > start_page or room_idx > 0:
                        self.rate_limiter.wait_between_pages()

                    page_flats = self.collect_page(
                        rooms=room_type, page=page
                    )

                    if not page_flats:
                        consecutive_empty += 1
                        if consecutive_empty >= 2:
                            logger.info(
                                "📭 2 пустые страницы подряд — "
                                "следующая комнатность"
                            )
                            break
                    else:
                        consecutive_empty = 0
                        room_flats.extend(page_flats)

                # Обогащаем деталями
                if room_flats and with_extra_data:
                    room_flats = self._enrich_with_details(
                        room_flats
                    )

                # Промежуточное сохранение
                if room_flats:
                    self._save_intermediate(
                        room_flats,
                        label=f"rooms_{room_type}",
                    )

                all_flats.extend(room_flats)

                logger.info(
                    f"📊 Итого rooms={room_type}: "
                    f"{len(room_flats)} объявлений"
                )

                # Пауза между типами комнатности
                if room_type != rooms[-1]:
                    self.rate_limiter.wait_between_sections()

        except CaptchaDetectedError:
            logger.error(
                "⛔ Парсинг остановлен (CAPTCHA). "
                "Сохраняем собранное."
            )
        finally:
            self.browser.stop()

        # Формируем DataFrame
        if not all_flats:
            logger.warning("❌ Не собрано ни одного объявления")
            return pd.DataFrame()

        df = pd.DataFrame(
            [flat.model_dump() for flat in all_flats]
        )

        # Дедупликация
        if "url" in df.columns:
            before = len(df)
            df.drop_duplicates(
                subset=["url"], keep="first", inplace=True
            )
            df.reset_index(drop=True, inplace=True)
            dupes = before - len(df)
            if dupes:
                logger.info(f"🔄 Удалено дубликатов: {dupes}")

        logger.info(f"\n{'═' * 50}")
        logger.info(
            f"✅ ИТОГО: {len(df)} уникальных объявлений"
        )
        logger.info(
            f"📊 Запросов выполнено: "
            f"{self.rate_limiter.total_requests}"
        )
        logger.info(
            f"🔒 CAPTCHA встречено: {self._captcha_count}"
        )
        logger.info(f"{'═' * 50}")

        return df
    
    def collect_details_resumable(
        self,
        csv_path: str,
        delay_range: tuple[float, float] = (30.0, 60.0),
        restart_every: int = 7,
        max_per_session: int = 50,
    ) -> pd.DataFrame:
        """
        Фаза 2: Дособирает детали для объявлений,
        у которых is_detail_parsed=False.

        Работает по resume-принципу — можно запускать
        многократно, каждый раз обрабатывая порцию.

        Args:
            csv_path: путь к CSV с данными из Фазы 1
            delay_range: пауза между объявлениями (сек)
            restart_every: рестарт браузера каждые N объявлений
            max_per_session: макс. объявлений за одну сессию
        """
        from forecasting_service.parsers.cian.detail_parser import (
            parse_detail_page,
        )

        df = pd.read_csv(csv_path, sep=";", encoding="utf-8")

        # Если колонки is_detail_parsed нет — добавляем
        if "is_detail_parsed" not in df.columns:
            df["is_detail_parsed"] = False

        # Находим необработанные
        pending = df[df["is_detail_parsed"] == False]
        total_pending = len(pending)

        if total_pending == 0:
            logger.info("✅ Все объявления уже обработаны")
            return df

        to_process = min(max_per_session, total_pending)
        logger.info(
            f"📋 Детали: {to_process}/{total_pending} "
            f"к обработке в этой сессии"
        )

        processed = 0

        try:
            self.browser.start()

            for idx in pending.index[:to_process]:
                url = df.at[idx, "url"]
                if not url or pd.isna(url):
                    continue

                try:
                    processed += 1
                    logger.info(
                        f"  [{processed}/{to_process}] "
                        f"{url[:60]}..."
                    )

                    # Рестарт браузера периодически
                    if (
                        processed > 1
                        and processed % restart_every == 0
                    ):
                        logger.info(
                            "🔄 Рестарт браузера..."
                        )
                        self.browser.restart_with_new_ua()
                        time.sleep(random.uniform(10, 20))

                    # Пауза
                    delay = random.uniform(*delay_range)
                    logger.debug(
                        f"  ⏳ Пауза {delay:.0f} сек..."
                    )
                    time.sleep(delay)

                    html = self.browser.get_page(
                        url, scroll=True
                    )

                    details = parse_detail_page(html)

                    # Обновляем DataFrame
                    for field, value in details.items():
                        if field in df.columns:
                            current = df.at[idx, field]
                            if pd.isna(current) or current == "":
                                df.at[idx, field] = value
                        else:
                            df[field] = None
                            df.at[idx, field] = value

                    df.at[idx, "is_detail_parsed"] = True

                except CaptchaDetectedError:
                    logger.warning(
                        f"🔒 CAPTCHA — сохраняем и выходим "
                        f"({processed} обработано)"
                    )
                    break

                except Exception as e:
                    logger.warning(f"  ❌ Ошибка: {e}")

                # Сохраняем после каждого объявления
                df.to_csv(
                    csv_path, index=False,
                    sep=";", encoding="utf-8",
                )

        finally:
            self.browser.stop()

        # Финальное сохранение
        df.to_csv(
            csv_path, index=False,
            sep=";", encoding="utf-8",
        )

        done = df["is_detail_parsed"].sum()
        total = len(df)
        logger.info(
            f"\n{'═' * 50}\n"
            f"📊 Прогресс: {done}/{total} "
            f"({done/total*100:.1f}%)\n"
            f"{'═' * 50}"
        )

        return df