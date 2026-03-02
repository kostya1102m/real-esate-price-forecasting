from typing import Optional
from pydantic import BaseModel, computed_field


class CianFlat(BaseModel):
    url: str = ""
    cian_id: Optional[int] = None

    price: Optional[int] = None

    total_meters: Optional[float] = None
    rooms_count: Optional[int] = None
    floor: Optional[int] = None
    floors_count: Optional[int] = None

    region: str = ""
    city: str = ""
    district: str = ""
    microdistrict: str = ""
    street: str = ""
    house_number: str = ""
    underground: str = ""
    residential_complex: str = ""
    address_raw: str = ""

    living_meters: Optional[float] = None
    kitchen_meters: Optional[float] = None
    ceiling_height: Optional[float] = None
    object_type: str = ""          # новостройка / Вторичка
    layout_type: str = ""          # смежная / изолированная / смежно-изолированная
    bathroom_type: str = ""        # раздельный / совмещённый
    bathroom_count: Optional[int] = None
    window_view: str = ""          # во двор / на улицу
    finish_type: str = ""          # без ремонта / косметический / евро / дизайнерский / предчистовая / чистовая
    balcony_count: Optional[int] = None
    loggia_count: Optional[int] = None
    has_furniture: Optional[bool] = None

    year_of_construction: Optional[int] = None
    house_material_type: str = ""  # кирпичный / монолитный / панельный / блочный / деревянный / монолитно-кирпичный / сталинский
    floor_type: str = ""           # тип перекрытий
    elevator_passenger: Optional[int] = None
    elevator_cargo: Optional[int] = None
    entrances_count: Optional[int] = None
    has_garbage_chute: Optional[bool] = None
    has_ramp: Optional[bool] = None
    has_concierge: Optional[bool] = None
    parking_type: str = ""         # наземная / многоуровневая / подземная
    heating_type: str = ""         # центральное / автономное
    is_emergency: Optional[bool] = None

    # о жилом комплексе
    jk_name: str = ""
    jk_class: str = ""             # комфорт / бизнес / элит
    jk_deadline: str = ""          # сдача комплекса
    developer: str = ""            # застройщик

    # инфа из росеестра
    cadastral_number: str = ""
    encumbrances: str = ""         # наличие обременений
    owners_count: Optional[int] = None

    title_raw: str = ""
    author: str = ""
    author_type: str = ""          # собственник / агент / застройщик
    is_detail_parsed: bool = False  # флаг: детальная страница обработана

    @computed_field
    @property
    def price_per_sqm(self) -> Optional[float]:
        if self.price and self.total_meters and self.total_meters > 0:
            return round(self.price / self.total_meters, 2)
        return None

    @computed_field
    @property
    def has_balcony(self) -> Optional[bool]:
        if self.balcony_count is not None or self.loggia_count is not None:
            return (self.balcony_count or 0) + (self.loggia_count or 0) > 0
        return None

    @computed_field
    @property
    def has_elevator(self) -> Optional[bool]:
        if self.elevator_passenger is not None or self.elevator_cargo is not None:
            return (self.elevator_passenger or 0) + (self.elevator_cargo or 0) > 0
        return None