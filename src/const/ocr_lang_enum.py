from enum import Enum
from typing import List

class OCRLanguage(Enum):
    """OCR支持的语言枚举"""
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

    @classmethod
    def get_supported_languages(cls) -> List[str]:
        """获取所有支持的语言列表"""
        return [member.value for member in cls]

