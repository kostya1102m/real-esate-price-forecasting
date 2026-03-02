# cкрипт для запуска сбора датасета с циана.

import argparse
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

# Настройка логов
logger.remove()
logger.add(
    sys.stderr,
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level:<8}</level> | "
        "{message}"
    ),
    level="INFO",
)
logger.add(
    "logs/collect_{time:YYYY-MM-DD}.log",
    format=(
        "{time:YYYY-MM-DD HH:mm:ss} | "
        "{level:<8} | "
        "{name}:{function}:{line} | "
        "{message}"
    ),
    level="DEBUG",
    rotation="10 MB",
)

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"


def main():
    parser = argparse.ArgumentParser(
        description="Сбор датасета квартир с ЦИАН (Selenium)"
    )
    parser.add_argument(
        "--location",
        type=str,
        default="Владивосток",
        help="Город (по умолчанию: Владивосток)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        nargs=2,
        default=[1, 3],
        metavar=("START", "END"),
        help="Диапазон страниц (по умолчанию: 1 3)",
    )
    parser.add_argument(
        "--rooms",
        nargs="+",
        default=["1", "2", "3"],
        help="Типы комнатности: studio 1 2 3 4 5",
    )
    parser.add_argument(
        "--no-extra",
        action="store_true",
        help="Не собирать доп. данные с детальных страниц",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Показывать окно браузера (для отладки)",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=5.0,
        help="Мин. пауза между страницами (сек, по умолчанию: 5)",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=15.0,
        help="Макс. пауза между страницами (сек, по умолчанию: 15)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Имя файла CSV для сохранения",
    )

        # В argparse добавляем:
    parser.add_argument(
        "--phase2",
        type=str,
        default=None,
        metavar="CSV_PATH",
        help="Фаза 2: дособрать детали из CSV (путь к файлу)",
    )
    parser.add_argument(
        "--detail-delay-min",
        type=float,
        default=30.0,
        help="Мин. пауза между деталями (сек, по умолчанию: 30)",
    )
    parser.add_argument(
        "--detail-delay-max",
        type=float,
        default=60.0,
        help="Макс. пауза между деталями (сек, по умолчанию: 60)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Макс. объявлений за сессию Фазы 2 (по умолчанию: 50)",
    )

    args = parser.parse_args()


    if args.phase2:
        logger.info("═" * 60)
        logger.info("📋 ФАЗА 2: СБОР ДЕТАЛЕЙ")
        logger.info(f"   Файл: {args.phase2}")
        logger.info(f"   Пауза: {args.detail_delay_min}-{args.detail_delay_max} сек")
        logger.info(f"   Батч:  {args.batch_size}")
        logger.info("═" * 60)

        from forecasting_service.parsers.cian.parser import CianParser

        cian = CianParser(
            location=args.location,
            headless=not args.no_headless,
        )

        df = cian.collect_details_resumable(
            csv_path=args.phase2,
            delay_range=(args.detail_delay_min, args.detail_delay_max),
            max_per_session=args.batch_size,
        )
        return


    # Преобразуем rooms
    rooms = []
    for r in args.rooms:
        if r == "studio":
            rooms.append("studio")
        else:
            rooms.append(int(r))

    logger.info("═" * 60)
    logger.info("🏠 СБОР ДАТАСЕТА КВАРТИР С ЦИАН")
    logger.info(f"   Город:        {args.location}")
    logger.info(f"   Страницы:     {args.pages[0]} - {args.pages[1]}")
    logger.info(f"   Комнатность:  {rooms}")
    logger.info(f"   Доп. данные:  {not args.no_extra}")
    logger.info(f"   Headless:     {not args.no_headless}")
    logger.info(f"   Задержка:     {args.min_delay}-{args.max_delay} сек")
    logger.info("═" * 60)

    from forecasting_service.parsers.cian.parser import CianParser

    cian = CianParser(
        location=args.location,
        headless=not args.no_headless,
        page_delay=(args.min_delay, args.max_delay),
        collect_extra_data=not args.no_extra,
    )

    df = cian.collect(
        rooms=tuple(rooms),
        start_page=args.pages[0],
        end_page=args.pages[1],
        with_extra_data=not args.no_extra,
    )

    if df.empty:
        logger.error("❌ Не удалось собрать данные!")
        logger.info("Рекомендации:")
        logger.info("  1. Запустите с --no-headless для визуальной отладки")
        logger.info("  2. Увеличьте задержки: --min-delay 8 --max-delay 20")
        logger.info("  3. Попробуйте позже (временная блокировка)")
        sys.exit(1)

    # Сохраняем
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = args.output or f"raw_cian_{args.location}_{timestamp}.csv"
    filepath = DATASETS_DIR / filename

    df.to_csv(filepath, index=False, sep=";", encoding="utf-8")

    logger.info(f"\n{'═' * 60}")
    logger.info(f"✅ Датасет сохранён: {filepath}")
    logger.info(f"   Записей:  {len(df)}")
    logger.info(f"   Колонок:  {len(df.columns)}")
    logger.info(f"   Колонки:  {list(df.columns)}")
    logger.info(f"{'═' * 60}")

    # Статистика
    if "price" in df.columns:
        prices = df["price"].dropna()
        if not prices.empty:
            logger.info(f"\n📊 Статистика цен:")
            logger.info(f"   Мин:      {prices.min():,.0f} ₽")
            logger.info(f"   Макс:     {prices.max():,.0f} ₽")
            logger.info(f"   Среднее:  {prices.mean():,.0f} ₽")
            logger.info(f"   Медиана:  {prices.median():,.0f} ₽")

    logger.info(f"\nПревью:\n{df.head().to_string()}")


if __name__ == "__main__":
    main()