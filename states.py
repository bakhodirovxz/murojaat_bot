"""FSM holatlari."""

from aiogram.fsm.state import State, StatesGroup


class Form(StatesGroup):
    """Fuqaro to'ldiradigan anketa."""

    fio = State()
    passport = State()
    jshshir = State()
    birth_date = State()
    address = State()
    phone = State()
    phone_extra = State()
    message = State()
    preview = State()


class Dialog(StatesGroup):
    """Admin ariza bo'yicha yozishmani olib borayotgan holat."""

    chatting = State()


class Export(StatesGroup):
    """Admin eksport uchun davr kiritayotgan holat."""

    custom_range = State()
