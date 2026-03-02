#парсинг детальной страницы объявления ЦИАН.

#структура страницы:
  #OfferSummaryInfoGroup (без --right) → "О квартире"
  #OfferSummaryInfoGroup (--right)     → "О доме"
  #b482a6--inner                       → "О ЖК"
  #RosreestrSection                    → "Информация из Росреестра"

#каждый блок содержит OfferSummaryInfoItem:
  #<p class="...gray60...">Название</p>
  #<p class="...text-primary...">Значение</p>

import re
from typing import Optional

from bs4 import BeautifulSoup, Tag
from loguru import logger


def parse_detail_page(html: str) -> dict:
    """
    парсит детальную страницу объявления.
    возвращает словарь с извлечёнными полями.
    """
    soup = BeautifulSoup(html, "lxml")
    details = {}

    # о квартире
    _parse_about_flat(soup, details)

    _parse_about_building(soup, details)

    # о жилом комплексе
    _parse_about_jk(soup, details)

    # инфа из росеестра
    _parse_rosreestr(soup, details)

    return details


def _parse_about_flat(soup: BeautifulSoup, details: dict) -> None:
    groups = soup.select(
        '[data-name="OfferSummaryInfoGroup"]'
    )

    flat_group = None
    for group in groups:
        header = group.select_one("h2")
        if header and "квартир" in header.get_text(strip=True).lower():
            flat_group = group
            break

    if not flat_group:
        return

    items = _extract_info_items(flat_group)

    FLAT_MAPPING = {
        "тип жилья": ("object_type", _str),
        "общая площадь": ("total_meters", _parse_area),
        "жилая площадь": ("living_meters", _parse_area),
        "площадь кухни": ("kitchen_meters", _parse_area),
        "высота потолков": ("ceiling_height", _parse_height),
        "санузел": ("_bathroom_raw", _str),
        "вид из окон": ("window_view", _str),
        "вид из окна": ("window_view", _str),
        "отделка": ("finish_type", _str),
        "ремонт": ("finish_type", _str),
        "балкон/лоджия": ("_balcony_raw", _str),
        "балкон": ("_balcony_raw", _str),
        "планировка": ("layout_type", _str),
        "мебель": ("has_furniture", _parse_furniture),
    }

    for name, value in items:
        name_lower = name.lower()
        for key, (field, parser) in FLAT_MAPPING.items():
            if key in name_lower:
                details[field] = parser(value)
                break

    
    if "_bathroom_raw" in details:
        _parse_bathroom(details.pop("_bathroom_raw"), details)

    if "_balcony_raw" in details:
        _parse_balcony(details.pop("_balcony_raw"), details)


def _parse_about_building(
    soup: BeautifulSoup, details: dict
) -> None:
    groups = soup.select(
        '[data-name="OfferSummaryInfoGroup"]'
    )

    building_group = None
    for group in groups:
        header = group.select_one("h2")
        if header and "доме" in header.get_text(strip=True).lower():
            building_group = group
            break

    if not building_group:
        return

    items = _extract_info_items(building_group)

    BUILDING_MAPPING = {
        "год постройки": ("year_of_construction", _parse_year),
        "количество лифтов": ("_elevator_raw", _str),
        "лифт": ("_elevator_raw", _str),
        "тип дома": ("house_material_type", _str),
        "тип перекрытий": ("floor_type", _str),
        "подъезды": ("entrances_count", _parse_int),
        "о подъезде": ("_entrance_info_raw", _str),
        "о\xa0подъезде": ("_entrance_info_raw", _str),
        "парковка": ("parking_type", _str),
        "отопление": ("heating_type", _str),
        "аварийность": ("is_emergency", _parse_emergency),
    }

    for name, value in items:
        name_lower = name.lower()
        for key, (field, parser) in BUILDING_MAPPING.items():
            if key in name_lower:
                details[field] = parser(value)
                break

    if "_elevator_raw" in details:
        _parse_elevators(details.pop("_elevator_raw"), details)

    if "_entrance_info_raw" in details:
        _parse_entrance_info(
            details.pop("_entrance_info_raw"), details
        )


def _parse_about_jk(
    soup: BeautifulSoup, details: dict
) -> None:
    """Парсит секцию 'О ЖК'."""
    # Ищем по заголовку "О ЖК"
    jk_section = None
    for h2 in soup.select("h2"):
        text = h2.get_text(strip=True)
        if text.startswith("О ЖК") or text.startswith("О\xa0ЖК"):
            jk_section = h2.find_parent(
                "div", class_=re.compile("inner")
            )
            break

    if not jk_section:
        return

    # извлекаем название ЖК из заголовка
    for h2 in jk_section.select("h2"):
        text = h2.get_text(strip=True)
        jk_match = re.search(r'[«""](.+?)[»""]', text)
        if jk_match:
            details["jk_name"] = jk_match.group(1)

    # парсим список характеристик
    items_list = jk_section.select("li")
    for li in items_list:
        spans = li.select("span")
        if len(spans) >= 2:
            name = spans[0].get_text(strip=True).lower()
            value = spans[-1].get_text(strip=True)

            if "сдача" in name:
                details["jk_deadline"] = value
            elif "класс" in name:
                details["jk_class"] = value
            elif "тип дома" in name:
                if "house_material_type" not in details:
                    details["house_material_type"] = value
            elif "парковка" in name:
                if "parking_type" not in details:
                    details["parking_type"] = value
            elif "отделка" in name:
                if "finish_type" not in details:
                    details["finish_type"] = value

        # застройщик (через ссылку)
        link = li.select_one('a[data-mark="Link"]')
        if link:
            label_span = li.select_one("span")
            if label_span and "застройщик" in label_span.get_text(strip=True).lower():
                details["developer"] = link.get_text(strip=True)


def _parse_rosreestr(
    soup: BeautifulSoup, details: dict
) -> None:
    """Парсит секцию 'Информация из Росреестра'."""
    rosreestr = soup.select_one(
        '[data-name="RosreestrSection"]'
    )
    if not rosreestr:
        return

    items = rosreestr.select(
        '[data-name="NameValueListItem"]'
    )

    for item in items:
        name_el = item.select_one("dt")
        value_el = item.select_one("dd")
        if not name_el or not value_el:
            continue

        name = name_el.get_text(strip=True).lower()
        value = value_el.get_text(strip=True)

        if "обременен" in name:
            details["encumbrances"] = value
        elif "площадь" in name:
            pass  # Уже есть из "О квартире"
        elif "собственник" in name:
            details["owners_count"] = _parse_int(value)
        elif "кадастровый" in name:
            details["cadastral_number"] = value


# Извлечение OfferSummaryInfoItem
def _extract_info_items(container: Tag) -> list[tuple[str, str]]:
    """
    Извлекает пары (название, значение) из OfferSummaryInfoItem.

    Структура:
      <div data-name="OfferSummaryInfoItem">
        <p class="...gray60...">Название</p>
        <p class="...text-primary...">Значение</p>
      </div>
    """
    items = []
    info_divs = container.select(
        '[data-name="OfferSummaryInfoItem"]'
    )

    for div in info_divs:
        paragraphs = div.select("p")
        if len(paragraphs) >= 2:
            name = paragraphs[0].get_text(strip=True)
            value = paragraphs[1].get_text(strip=True)
            items.append((name, value))

    return items


# Парсеры значений
def _str(value: str) -> str:
    return value.strip()


def _parse_area(value: str) -> Optional[float]:
    """'26,7 м²' → 26.7"""
    match = re.search(r'([\d]+[,.]?\d*)', value)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def _parse_height(value: str) -> Optional[float]:
    """'2,87 м' → 2.87"""
    return _parse_area(value)


def _parse_year(value: str) -> Optional[int]:
    """'1973' → 1973"""
    match = re.search(r'((?:19|20)\d{2})', value)
    if match:
        return int(match.group(1))
    return None


def _parse_int(value: str) -> Optional[int]:
    match = re.search(r'(\d+)', value)
    if match:
        return int(match.group(1))
    return None


def _parse_emergency(value: str) -> Optional[bool]:
    lower = value.lower()
    if "нет" in lower:
        return False
    if "да" in lower or "есть" in lower:
        return True
    return None


def _parse_furniture(value: str) -> Optional[bool]:
    lower = value.lower()
    if "с мебелью" in lower or "есть" in lower:
        return True
    if "без мебели" in lower or "нет" in lower:
        return False
    return None


def _parse_bathroom(raw: str, details: dict) -> None:
    """
    '1 раздельный' → bathroom_type='раздельный', bathroom_count=1
    'Совмещённый'  → bathroom_type='совмещённый', bathroom_count=1
    """
    lower = raw.lower()
    count = _parse_int(raw)
    details["bathroom_count"] = count or 1

    if "раздельн" in lower:
        details["bathroom_type"] = "раздельный"
    elif "совмещ" in lower:
        details["bathroom_type"] = "совмещённый"
    else:
        details["bathroom_type"] = raw


def _parse_balcony(raw: str, details: dict) -> None:
    """
    '1 балкон'           → balcony_count=1
    '2 лоджии'           → loggia_count=2
    '1 балкон, 1 лоджия' → balcony_count=1, loggia_count=1
    """
    lower = raw.lower()

    balcony_match = re.search(r'(\d+)\s*балкон', lower)
    if balcony_match:
        details["balcony_count"] = int(balcony_match.group(1))
    elif "балкон" in lower:
        details["balcony_count"] = 1

    loggia_match = re.search(r'(\d+)\s*лоджи', lower)
    if loggia_match:
        details["loggia_count"] = int(loggia_match.group(1))
    elif "лоджи" in lower:
        details["loggia_count"] = 1


def _parse_elevators(raw: str, details: dict) -> None:
    """
    '1 пассажирский'              → elevator_passenger=1
    '2 пассажирских, 1 грузовой'  → elevator_passenger=2, elevator_cargo=1
    """
    lower = raw.lower()

    pass_match = re.search(r'(\d+)\s*пассажирск', lower)
    if pass_match:
        details["elevator_passenger"] = int(pass_match.group(1))

    cargo_match = re.search(r'(\d+)\s*грузов', lower)
    if cargo_match:
        details["elevator_cargo"] = int(cargo_match.group(1))

    # если просто "Есть" без деталей
    if not pass_match and not cargo_match:
        if "есть" in lower:
            details["elevator_passenger"] = 1


def _parse_entrance_info(raw: str, details: dict) -> None:
    """
    'Есть мусоропровод' → has_garbage_chute=True
    'Есть консьерж'     → has_concierge=True
    """
    lower = raw.lower()
    if "мусоропровод" in lower:
        details["has_garbage_chute"] = True
    if "консьерж" in lower:
        details["has_concierge"] = True
    if "пандус" in lower:
        details["has_ramp"] = True