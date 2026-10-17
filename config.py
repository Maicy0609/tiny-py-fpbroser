"""Static configuration: paths, locale maps, device labels and font sets."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "profiles"
DATA_DIR = BASE_DIR / "data"
IPINFO_URL = "https://ipinfo.io/json"
# With a proxy, WebRTC must use UDP only through it, otherwise STUN reveals the real IP.
# Without a proxy the exit IP is the real IP, so only local addresses need hiding.
WEBRTC_POLICY_PROXIED = "disable_non_proxied_udp"
WEBRTC_POLICY_DIRECT = "default_public_interface_only"
REQUIRED_KEYS = {"name", "created_at", "network", "browser", "fingerprint"}

COUNTRY_LOCALE = {
    "US": "en-US", "GB": "en-GB", "CA": "en-CA", "AU": "en-AU", "IN": "en-IN",
    "SG": "en-SG", "DE": "de-DE", "FR": "fr-FR", "ES": "es-ES", "MX": "es-MX",
    "IT": "it-IT", "NL": "nl-NL", "BR": "pt-BR", "RU": "ru-RU", "TR": "tr-TR",
    "JP": "ja-JP", "KR": "ko-KR", "CN": "zh-CN", "TW": "zh-TW", "HK": "zh-HK",
}
MIC_LABELS = [
    "Microphone (Realtek High Definition Audio)",
    "Microphone Array (Intel Smart Sound Technology)",
    "Headset Microphone (Logitech USB Headset)",
]
SPEAKER_LABELS = [
    "Speakers (Realtek High Definition Audio)",
    "Headphones (Realtek High Definition Audio)",
    "Speakers (Logitech USB Headset)",
]
CAMERA_LABELS = ["Integrated Camera", "HD Webcam", "Logitech HD Webcam C270 (046d:0825)"]
# Default Windows 10/11 speech voices per locale (en-US is always installed).
SPEECH_VOICES = {
    "en-US": ["Microsoft David - English (United States)", "Microsoft Zira - English (United States)",
              "Microsoft Mark - English (United States)"],
    "en-GB": ["Microsoft Hazel - English (United Kingdom)", "Microsoft George - English (United Kingdom)"],
    "en-CA": ["Microsoft Linda - English (Canada)"],
    "en-AU": ["Microsoft Catherine - English (Australia)"],
    "en-IN": ["Microsoft Heera - English (India)"],
    "de-DE": ["Microsoft Hedda - German (Germany)", "Microsoft Stefan - German (Germany)"],
    "fr-FR": ["Microsoft Hortense - French (France)", "Microsoft Paul - French (France)"],
    "es-ES": ["Microsoft Helena - Spanish (Spain)", "Microsoft Pablo - Spanish (Spain)"],
    "es-MX": ["Microsoft Sabina - Spanish (Mexico)", "Microsoft Raul - Spanish (Mexico)"],
    "it-IT": ["Microsoft Elsa - Italian (Italy)", "Microsoft Cosimo - Italian (Italy)"],
    "nl-NL": ["Microsoft Frank - Dutch (Netherlands)"],
    "pt-BR": ["Microsoft Maria - Portuguese (Brazil)", "Microsoft Daniel - Portuguese (Brazil)"],
    "ru-RU": ["Microsoft Irina - Russian (Russia)", "Microsoft Pavel - Russian (Russia)"],
    "tr-TR": ["Microsoft Tolga - Turkish (Turkey)"],
    "ja-JP": ["Microsoft Haruka - Japanese (Japan)", "Microsoft Ichiro - Japanese (Japan)"],
    "ko-KR": ["Microsoft Heami - Korean (Korea)"],
    "zh-CN": ["Microsoft Huihui - Chinese (Simplified, PRC)", "Microsoft Kangkang - Chinese (Simplified, PRC)",
              "Microsoft Yaoyao - Chinese (Simplified, PRC)"],
    "zh-TW": ["Microsoft Hanhan - Chinese (Traditional, Taiwan)", "Microsoft Zhiwei - Chinese (Traditional, Taiwan)"],
    "zh-HK": ["Microsoft Tracy - Chinese (Traditional, Hong Kong)", "Microsoft Danny - Chinese (Traditional, Hong Kong)"],
}

# Font set: fonts a stock Windows 10/11 install ships with (all locales), plus the extras that
# come with a language pack. Every other installed font is hidden from pages.
WINDOWS_FONTS = (
    "Arial", "Arial Black", "Bahnschrift", "Calibri", "Cambria", "Cambria Math", "Candara",
    "Cascadia Code", "Cascadia Mono", "Comic Sans MS", "Consolas", "Constantia", "Corbel",
    "Courier New", "Ebrima", "Franklin Gothic Medium", "Gabriola", "Gadugi", "Georgia",
    "HoloLens MDL2 Assets", "Impact", "Ink Free", "Javanese Text", "Leelawadee UI",
    "Lucida Console", "Lucida Sans Unicode", "Malgun Gothic", "Marlett", "Microsoft Himalaya",
    "Microsoft JhengHei", "Microsoft JhengHei UI", "Microsoft New Tai Lue", "Microsoft PhagsPa",
    "Microsoft Sans Serif", "Microsoft Tai Le", "Microsoft YaHei", "Microsoft YaHei UI",
    "Microsoft Yi Baiti", "MingLiU-ExtB", "PMingLiU-ExtB", "MingLiU_HKSCS-ExtB", "Mongolian Baiti",
    "MS Gothic", "MS PGothic", "MS UI Gothic", "MV Boli", "Myanmar Text", "Nirmala UI",
    "Palatino Linotype", "Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe Print", "Segoe Script",
    "Segoe UI", "Segoe UI Emoji", "Segoe UI Historic", "Segoe UI Symbol", "Segoe UI Variable",
    "SimSun", "NSimSun", "SimSun-ExtB", "Sitka", "Sitka Banner", "Sitka Display", "Sitka Heading",
    "Sitka Small", "Sitka Subheading", "Sitka Text", "Sylfaen", "Symbol", "Tahoma",
    "Times New Roman", "Trebuchet MS", "Verdana", "Webdings", "Wingdings", "Yu Gothic",
    "Yu Gothic UI",
)
LOCALE_FONTS = {
    "zh-CN": ("SimHei", "KaiTi", "FangSong", "DengXian"),
    "zh-TW": ("PMingLiU", "MingLiU", "DFKai-SB"),
    "zh-HK": ("PMingLiU", "MingLiU", "DFKai-SB", "MingLiU_HKSCS"),
    "ja-JP": ("Meiryo", "Meiryo UI", "MS Mincho", "MS PMincho", "Yu Mincho", "BIZ UDGothic",
              "BIZ UDPGothic", "BIZ UDMincho", "BIZ UDPMincho"),
    "ko-KR": ("Batang", "BatangChe", "Dotum", "DotumChe", "Gulim", "GulimChe", "Gungsuh", "GungsuhChe"),
}
# Weight/style words: "Segoe UI Semibold" counts as part of the "Segoe UI" family.
STYLE_WORDS = {
    "bold", "italic", "oblique", "regular", "light", "semilight", "semibold", "black", "medium",
    "thin", "extralight", "extrabold", "condensed", "semicondensed",
}
