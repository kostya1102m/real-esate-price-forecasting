from pathlib import Path

# базовые пути
BASE_DIR = Path(__file__).resolve().parent
DATASETS_DIR = BASE_DIR / "datasets"
ARTIFACTS_DIR = BASE_DIR / "artifacts"

# настройки парсинга для библиотеки циан парсера (cianparser)
LOCATION = "Владивосток"
DEAL_TYPE = "sale"

# комнатность для парсинга (все типы)
ROOMS_TO_PARSE = ("studio", 1, 2, 3, 4, 5)

# настройки постраничного парсинга
DEFAULT_START_PAGE = 1
DEFAULT_END_PAGE = 54  # циан отдаёт макс ~54 страницы

# задержка для повторного парсинга
PARSE_WITH_EXTRA_DATA = True  # возращает living_meters, kitchen_meters, year и т.д.