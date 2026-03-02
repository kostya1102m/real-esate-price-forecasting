import re
import json
from typing import Optional

from bs4 import BeautifulSoup, Tag
from loguru import logger

from forecasting_service.parsers.cian.models import CianFlat

from forecasting_service.parsers.cian.detail_parser import (
    parse_detail_page,
)


def parse_listing_page(html: str) -> list[CianFlat]:
    """
    Парсит страницу листинга ЦИАН.
    Извлекает все карточки объявлений.
    """
    soup = BeautifulSoup(html, "lxml")

    # ищем карточки
    cards = soup.select('[data-name="CardComponent"]')

    if not cards:
        logger.warning("Карточки CardComponent не найдены")
        return []

    flats = []
    for card in cards:
        try:
            flat = _parse_card(card)
            if flat and flat.url:
                flats.append(flat)
        except Exception as e:
            logger.debug(f"Ошибка парсинга карточки: {e}")

    return flats


def is_empty_listing(html: str) -> bool:
    html_lower = html[:10000].lower()
    empty_indicators = [
        "по вашему запросу ничего не найдено",
        "нет объявлений",
        "объявления не найдены",
        "попробуйте изменить параметры",
        "ничего не нашлось",
    ]
    return any(ind in html_lower for ind in empty_indicators)


def _parse_card(card: Tag) -> Optional[CianFlat]:
    url = _extract_url(card)
    cian_id = _extract_cian_id(url)

    title = _extract_title(card)
    rooms, total_meters, floor, floors_count = _parse_title(title)

    price = _extract_price(card)

    geo_data = _extract_geo_labels(card)

    residential_complex = _extract_jk(card)

    underground = _extract_underground(card)

    return CianFlat(
        url=url,
        cian_id=cian_id,
        price=price,
        total_meters=total_meters,
        rooms_count=rooms,
        floor=floor,
        floors_count=floors_count,
        district=geo_data.get("district", ""),
        street=geo_data.get("street", ""),
        house_number=geo_data.get("house", ""),
        underground=underground,
        residential_complex=residential_complex,
        title_raw=title,
        address_raw=geo_data.get("full_address", ""),
    )


def _extract_url(card: Tag) -> str:
    link = (
        card.select_one(
            '[data-name="LinkArea"] a[href*="/flat/"]'
        )
        or card.select_one('a[href*="/flat/"]')
        or card.select_one('a[href*="cian.ru"]')
    )

    if not link:
        return ""

    href = link.get("href", "")

    clean_url = re.sub(r'\?mlSearchSessionGuid=[^&]*', '', href)

    return clean_url


def _extract_cian_id(url: str) -> Optional[int]:
    match = re.search(r'/flat/(\d+)', url)
    if match:
        return int(match.group(1))
    return None


def _extract_title(card: Tag) -> str:
    title_el = card.select_one('[data-mark="OfferTitle"]')
    if title_el:
        return title_el.get_text(strip=True)
    return ""


def _extract_price(card: Tag) -> Optional[int]:
    price_el = card.select_one('[data-mark="MainPrice"]')
    if not price_el:
        return None

    price_text = price_el.get_text(strip=True)
    digits = re.sub(r'[^\d]', '', price_text)
    return int(digits) if digits else None


def _extract_geo_labels(card: Tag) -> dict:
    """
    Извлекает адрес из цепочки GeoLabel.

    Цепочка выглядит так:
      GeoLabel[0]: "Приморский край" (регион)
      GeoLabel[1]: "Владивосток" (город)
      GeoLabel[2]: "р-н Первомайский" (район)
      GeoLabel[3]: "мкр. Чуркин" (микрорайон) — опционально
      GeoLabel[4]: "Харьковская улица" (улица)
      GeoLabel[5]: "1к1" (дом)

    Иногда микрорайона нет, иногда нет улицы/дома.
    """
    geo_links = card.select('[data-name="GeoLabel"]')

    result = {
        "region": "",
        "city": "",
        "district": "",
        "microdistrict": "",
        "street": "",
        "house": "",
        "full_address": "",
    }

    if not geo_links:
        return result

    labels = [link.get_text(strip=True) for link in geo_links]
    result["full_address"] = ", ".join(labels)

    for link in geo_links:
        text = link.get_text(strip=True)
        href = link.get("href", "")

        if "region=" in href and not result["region"]:
            if not result["region"]:
                result["region"] = text
            elif not result["city"]:
                result["city"] = text

        elif "district%5B" in href or "district[" in href:
            if not result["district"]:
                result["district"] = text
            elif not result["microdistrict"]:
                result["microdistrict"] = text

        elif "street%5B" in href or "street[" in href:
            result["street"] = text

        elif "house%5B" in href or "house[" in href:
            result["house"] = text


    if not result["district"] and len(labels) >= 3:
        _parse_geo_by_position(labels, result)

    return result


def _parse_geo_by_position(
    labels: list[str], result: dict
) -> None:
    """
    Fallback-парсинг адреса по позиции в списке.

    Типичные паттерны:
    [край, город, район, улица, дом]
    [край, город, район, микрорайон, улица, дом]
    [край, город, район, дом]  (без улицы)
    """
    # Определяем элементы по содержимому
    for i, label in enumerate(labels):
        lower = label.lower()

        if i == 0 and ("край" in lower or "область" in lower):
            result["region"] = label
        elif i == 1 and not result["city"]:
            result["city"] = label
        elif "р-н " in lower or "район" in lower:
            if not result["district"]:
                result["district"] = label
        elif "мкр." in lower or "микрорайон" in lower:
            result["microdistrict"] = label
        elif (
            "улица" in lower
            or "проспект" in lower
            or "бульвар" in lower
            or "переулок" in lower
            or "шоссе" in lower
            or "набережная" in lower
            or "проезд" in lower
            or "аллея" in lower
        ):
            result["street"] = label
        elif (
            i == len(labels) - 1
            and not result["house"]
            and _looks_like_house_number(label)
        ):
            result["house"] = label


def _looks_like_house_number(text: str) -> bool:
    """Проверяет, похоже ли на номер дома."""
    # "1к1", "15", "23А", "5/2", "10 к2" и т.д.
    return bool(
        re.match(
            r'^[\d]+[а-яА-Яa-zA-Z/к\s]*\d*$',
            text.strip()
        )
    )


def _extract_jk(card: Tag) -> str:
    """Извлекает название ЖК."""
    jk_link = card.select_one('a[class*="jk"]')
    if jk_link:
        text = jk_link.get_text(strip=True)
        text = re.sub(r'^ЖК\s*[«""]?\s*', '', text)
        text = re.sub(r'[»""]$', '', text)
        return text.strip()
    return ""


def _extract_underground(card: Tag) -> str:
    """Извлекает название станции метро."""
    underground_el = card.select_one(
        '[data-name*="nderground"], [class*="underground"]'
    )
    if underground_el:
        text = underground_el.get_text(strip=True)
        text = re.sub(r'\d+\s*мин.*$', '', text).strip()
        return text

    return ""


def _parse_title(title: str) -> tuple[
    Optional[int],
    Optional[float],
    Optional[int],
    Optional[int],
]:
    """
    Парсит заголовок объявления.

    Примеры:
      "1-комн. квартира, 32 м², 7/24 этаж" → (1, 32.0, 7, 24)
      "Студия, 25,5 м², 3/9 этаж" → (0, 25.5, 3, 9)
      "Гостинка с шикарным видом" → (None, None, None, None)
      "2-комн. кв., 54,3 м², 5/9 этаж" → (2, 54.3, 5, 9)

    Returns:
        (rooms_count, total_meters, floor, floors_count)
    """
    rooms = None
    total_meters = None
    floor = None
    floors_count = None

    rooms_match = re.search(r'(\d+)-комн', title)
    if rooms_match:
        rooms = int(rooms_match.group(1))
    elif 'студия' in title.lower():
        rooms = 0

    meters_match = re.search(r'([\d]+[,.]?\d*)\s*м²', title)
    if meters_match:
        meters_str = meters_match.group(1).replace(',', '.')
        total_meters = float(meters_str)

    floor_match = re.search(r'(\d+)\s*/\s*(\d+)\s*эт', title)
    if floor_match:
        floor = int(floor_match.group(1))
        floors_count = int(floor_match.group(2))

    return rooms, total_meters, floor, floors_count



# def parse_detail_page(html: str) -> dict:
#     """
#     Парсит детальную страницу объявления.
#     Извлекает дополнительные поля:
#     living_meters, kitchen_meters, year, material, finish и т.д.
#     """
#     soup = BeautifulSoup(html, "lxml")
#     details = {}

#     # Стратегия 1: ищем блоки с характеристиками
#     # ЦИАН использует структуру "Название: Значение"
#     _parse_factoids(soup, details)

#     # Стратегия 2: ищем в тексте страницы
#     if not details:
#         _parse_from_text(soup, details)

#     return details


# def _parse_factoids(soup: BeautifulSoup, details: dict) -> None:
#     """Парсит блоки характеристик."""
#     # Ищем все элементы с data-name содержащим Info/Factoid
#     info_items = soup.select(
#         '[data-name="ObjectFactoidsItem"], '
#         '[data-name*="Info"], '
#         '[data-name*="Feature"]'
#     )

#     for item in info_items:
#         text = item.get_text(separator=" | ", strip=True).lower()
#         _extract_detail_from_text(text, item, details)

#     # Также ищем в таблицах/списках характеристик
#     all_text_blocks = soup.select(
#         '[class*="info"], [class*="detail"], [class*="feature"]'
#     )

#     for block in all_text_blocks:
#         text = block.get_text(separator=" | ", strip=True).lower()
#         _extract_detail_from_text(text, block, details)


# def _extract_detail_from_text(
#     text: str,
#     element: Tag,
#     details: dict,
# ) -> None:
#     """Извлекает детали из текстового блока."""
#     # Жилая площадь
#     if 'жилая' in text and 'living_meters' not in details:
#         val = _extract_float_from_text(text)
#         if val:
#             details['living_meters'] = val

#     # Кухня
#     if 'кухн' in text and 'kitchen_meters' not in details:
#         val = _extract_float_from_text(text)
#         if val:
#             details['kitchen_meters'] = val

#     # Год постройки
#     if (
#         ('год' in text and 'постройки' in text)
#         or 'построен' in text
#     ) and 'year_of_construction' not in details:
#         year_match = re.search(r'(19\d{2}|20\d{2})', text)
#         if year_match:
#             details['year_of_construction'] = int(
#                 year_match.group(1)
#             )

#     # Материал стен
#     material_keywords = {
#         'кирпич': 'Кирпич',
#         'панель': 'Панель',
#         'монолитно-кирпич': 'Монолитно-кирпичный',
#         'монолит': 'Монолит',
#         'блочн': 'Блочный',
#         'деревян': 'Деревянный',
#     }
#     if (
#         ('материал' in text or 'тип дома' in text)
#         and 'house_material_type' not in details
#     ):
#         for keyword, value in material_keywords.items():
#             if keyword in text:
#                 details['house_material_type'] = value
#                 break

#     # Ремонт/отделка
#     finish_keywords = {
#         'без отделки': 'Без отделки',
#         'чернов': 'Черновая',
#         'чистов': 'Чистовая',
#         'предчистов': 'Предчистовая',
#         'евро': 'Евроремонт',
#         'дизайнер': 'Дизайнерский',
#         'космети': 'Косметический',
#         'капитальн': 'Капитальный',
#     }
#     if (
#         ('ремонт' in text or 'отделка' in text)
#         and 'finish_type' not in details
#     ):
#         for keyword, value in finish_keywords.items():
#             if keyword in text:
#                 details['finish_type'] = value
#                 break

#     # Отопление
#     if 'отопление' in text and 'heating_type' not in details:
#         if 'центральн' in text:
#             details['heating_type'] = 'Центральное'
#         elif 'автономн' in text or 'индивидуальн' in text:
#             details['heating_type'] = 'Автономное'


# def _parse_from_text(soup: BeautifulSoup, details: dict) -> None:
#     """Fallback: ищем характеристики в общем тексте страницы."""
#     full_text = soup.get_text(separator=" ", strip=True).lower()

#     # Жилая площадь
#     if 'living_meters' not in details:
#         match = re.search(
#             r'жилая\s*(?:площадь)?[\s:]+(\d+[,.]?\d*)\s*м',
#             full_text,
#         )
#         if match:
#             details['living_meters'] = float(
#                 match.group(1).replace(',', '.')
#             )

#     # Кухня
#     if 'kitchen_meters' not in details:
#         match = re.search(
#             r'кухн[яи]\s*[\s:]+(\d+[,.]?\d*)\s*м',
#             full_text,
#         )
#         if match:
#             details['kitchen_meters'] = float(
#                 match.group(1).replace(',', '.')
#             )

#     # Год постройки
#     if 'year_of_construction' not in details:
#         match = re.search(
#             r'(?:год\s*постройки|построен\s*в?)\s*[\s:]+(\d{4})',
#             full_text,
#         )
#         if match:
#             year = int(match.group(1))
#             if 1900 <= year <= 2030:
#                 details['year_of_construction'] = year


# def _extract_float_from_text(text: str) -> Optional[float]:
#     """Извлекает число с плавающей точкой из текста."""
#     match = re.search(r'(\d+[,.]?\d*)\s*м', text)
#     if match:
#         return float(match.group(1).replace(',', '.'))
#     return None