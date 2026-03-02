REGIONS = {
    "Владивосток": 4701,
    "Москва": 1,
    "Санкт-Петербург": 2,
    "Новосибирск": 4897,
    "Екатеринбург": 4743,
    "Казань": 4777,
    "Хабаровск": 4680,
}

ROOM_PARAMS = {
    "studio": "room9=1",
    0: "room9=1",   # студия как число
    1: "room1=1",
    2: "room2=1",
    3: "room3=1",
    4: "room4=1",
    5: "room5=1",
    6: "room6=1",
}

DEAL_TYPES = {
    "sale": "sale",
    "rent_long": "rent",
    "rent_short": "rent",
}

# базовый URL листинга
BASE_LISTING_URL = "https://cian.ru/cat.php"

LISTING_CARD_SELECTOR = '[data-name="CardComponent"]'

MAX_PAGES = 54

OFFERS_PER_PAGE = 28