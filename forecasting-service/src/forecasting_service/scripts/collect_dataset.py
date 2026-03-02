# cкрипт для запуска сбора датасета с циана.

import argparse
import logging
import sys

from forecasting_service.data.collector import (
    CianDataCollector,
    collect_all_rooms_separately,
)
from forecasting_service.config import (
    LOCATION,
    DEFAULT_START_PAGE,
    DEFAULT_END_PAGE,
    ROOMS_TO_PARSE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Сбор датасета квартир Владивостока с ЦИАН"
    )
    parser.add_argument(
        "--location",
        type=str,
        default=LOCATION,
        help=f"Город (по умолчанию: {LOCATION})",
    )
    parser.add_argument(
        "--pages",
        type=int,
        nargs=2,
        default=[DEFAULT_START_PAGE, DEFAULT_END_PAGE],
        metavar=("START", "END"),
        help=f"Диапазон страниц (по умолчанию: {DEFAULT_START_PAGE} {DEFAULT_END_PAGE})",
    )
    parser.add_argument(
        "--no-extra",
        action="store_true",
        help="Не собирать дополнительные данные (быстрее, но меньше признаков)",
    )
    parser.add_argument(
        "--separate",
        action="store_true",
        default=True,
        help="Собирать по комнатности раздельно (надёжнее, по умолчанию)",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("СБОР ДАТАСЕТА КВАРТИР С ЦИАН")
    logger.info(f"Город: {args.location}")
    logger.info(f"Страницы: {args.pages[0]} - {args.pages[1]}")
    logger.info(f"Доп. данные: {not args.no_extra}")
    logger.info(f"Раздельный сбор: {args.separate}")
    logger.info("=" * 60)

    with_extra = not args.no_extra

    if args.separate:
        df = collect_all_rooms_separately(
            location=args.location,
            start_page=args.pages[0],
            end_page=args.pages[1],
            with_extra_data=with_extra,
        )
    else:
        collector = CianDataCollector(location=args.location)
        df = collector.collect(
            rooms=ROOMS_TO_PARSE,
            start_page=args.pages[0],
            end_page=args.pages[1],
            with_extra_data=with_extra,
        )
        collector.save_raw_dataset(df)

    logger.info(f"\nИтого собрано: {len(df)} объявлений")
    if not df.empty:
        logger.info(f"Колонки: {list(df.columns)}")
        logger.info(f"\nПревью данных:\n{df.head()}")


if __name__ == "__main__":
    main()