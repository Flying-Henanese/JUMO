from enum import Enum

class OCRLanguage(Enum):
    CH = "ch"
    CH_SERVER = "ch_server"
    CH_LITE = "ch_lite"
    EN = "en"
    KOREAN = "korean"
    JAPAN = "japan"
    CHINESE_CHT = "chinese_cht"
    TA = "ta"
    TE = "te"
    KA = "ka"

    @classmethod
    def get_default(cls):
        return cls.CH

