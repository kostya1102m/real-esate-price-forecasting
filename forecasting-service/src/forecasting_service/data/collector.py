#модуль сбора данных с циан парсером
# оборачивает библиотеку для формирования датасета.

import logging
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional

import cianparser

from forecasting_service.config import (
    LOCATION,
    DEAL_TYPE,
    ROOMS_TO_PARSE,
    DEFAULT_START_PAGE,
    DEFAULT_END_PAGE,
    PARSE_WITH_EXTRA_DATA,
    DATASETS_DIR,
)

logger = logging.getLogger(__name__)


class CianDataCollector:

    def __init__(
        self,
        location: str = LOCATION,
        proxies: Optional[list] = None,
    ):
        self.location = location
        self.parser = cianparser.CianParser(location=location, proxies=proxies)
        self.raw_data: list[dict] = []

    def collect(
        self,
        rooms: tuple = ROOMS_TO_PARSE,
        start_page: int = DEFAULT_START_PAGE,
        end_page: int = DEFAULT_END_PAGE,
        with_extra_data: bool = PARSE_WITH_EXTRA_DATA,
    ) -> pd.DataFrame:
        """
        Собирает данные о квартирах на продажу.

        Args:
            rooms: типы комнатности для парсинга
            start_page: начальная страница
            end_page: конечная страница
            with_extra_data: собирать ли доп. данные (год постройки, тип дома и т.д.)

        Returns:
            pd.DataFrame с собранными данными
        """
        logger.info(
            f"Начинаем сбор данных: location={self.location}, "
            f"rooms={rooms}, pages={start_page}-{end_page}, "
            f"extra_data={with_extra_data}"
        )

        additional_settings = {
            "start_page": start_page,
            "end_page": end_page,
            "only_flat": True,       # Только квартиры (не апартаменты)
        }

        try:
            data = self.parser.get_flats(
                deal_type=DEAL_TYPE,
                rooms=rooms,
                with_saving_csv=False,
                with_extra_data=with_extra_data,
                additional_settings=additional_settings,
            )
            self.raw_data = data
            logger.info(f"Собрано {len(data)} объявлений")

        except Exception as e:
            logger.error(f"Ошибка при парсинге: {e}")
            raise

        df = pd.DataFrame(self.raw_data)
        return df

    def save_raw_dataset(
        self,
        df: pd.DataFrame,
        filename: Optional[str] = None,
    ) -> Path:

        DATASETS_DIR.mkdir(parents=True, exist_ok=True)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw_vladivostok_{timestamp}.csv"

        filepath = DATASETS_DIR / filename
        df.to_csv(filepath, index=False, sep=";", encoding="utf-8")
        logger.info(f"Датасет сохранён: {filepath} ({len(df)} записей)")

        return filepath


def collect_all_rooms_separately(
    location: str = LOCATION,
    proxies: Optional[list] = None,
    start_page: int = DEFAULT_START_PAGE,
    end_page: int = DEFAULT_END_PAGE,
    with_extra_data: bool = PARSE_WITH_EXTRA_DATA,
) -> pd.DataFrame:
    
    collector = CianDataCollector(location=location, proxies=proxies)
    all_dfs = []

    for room_type in ROOMS_TO_PARSE:
        logger.info(f"--- Сбор данных: комнатность = {room_type} ---")
        try:
            rooms_param = room_type if isinstance(room_type, (int, str)) else room_type

            df = collector.collect(
                rooms=rooms_param,
                start_page=start_page,
                end_page=end_page,
                with_extra_data=with_extra_data,
            )

            if not df.empty:
                all_dfs.append(df)
                # Промежуточное сохранение
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                collector.save_raw_dataset(
                    df,
                    filename=f"raw_vladivostok_rooms_{room_type}_{timestamp}.csv"
                )

        except Exception as e:
            logger.error(f"Ошибка при сборе rooms={room_type}: {e}")
            continue

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        # Удаляем дубликаты по URL
        combined_df.drop_duplicates(subset=["url"], keep="first", inplace=True)
        collector.save_raw_dataset(combined_df, filename=f"raw_vladivostok_combined_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        return combined_df

    return pd.DataFrame()