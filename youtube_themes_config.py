"""
Конфиг 5 тем для Этапа 1 (YouTube Shorts).
У каждой темы — ключевая тема и ~20 хэштегов (RU + EN) для популярного контента.
"""

YOUTUBE_THEMES = [
    {
        "name": "Юмор",
        "description": "Смешные видео, комедия, шутки, приколы",
        "folder": "humor",
        "hashtags": [
            "#смех", "#приколы", "#шортс", "#юмор", "#ржака", "#мемы", "#смешное",
            "#комедия", "#прикол", "#реакция",
            "#funny", "#memes", "#comedy", "#viral", "#shorts", "#lol", "#fails",
            "#hilarious", "#trending", "#fyp",
        ],
    },
    {
        "name": "Бизнес",
        "description": "Бизнес, предпринимательство, успех, деньги",
        "folder": "business",
        "hashtags": [
            "#бизнес", "#деньги", "#успех", "#бизнесидеи", "#стартап", "#предприниматель",
            "#инвестиции", "#трейдинг", "#криптовалюта", "#заработок",
            "#business", "#money", "#success", "#entrepreneur", "#startup", "#investing",
            "#motivation", "#hustle", "#wealth", "#finance",
        ],
    },
    {
        "name": "Лайфстайл",
        "description": "Образ жизни, повседневность, влоги",
        "folder": "lifestyle",
        "hashtags": [
            "#лайфстайл", "#влог", "#деньизжизни", "#красота", "#мода", "#путешествия",
            "#еда", "#рецепты", "#рукоделие", "#тренды",
            "#lifestyle", "#vlog", "#dayinmylife", "#beauty", "#fashion", "#travel",
            "#food", "#recipe", "#diy", "#trend",
        ],
    },
    {
        "name": "Технологии",
        "description": "Технологии, гаджеты, инновации",
        "folder": "tech",
        "hashtags": [
            "#технологии", "#гаджеты", "#айфон", "#андроид", "#игры", "#программирование",
            "#айти", "#обзор", "#новинки", "#софт",
            "#tech", "#gadgets", "#iphone", "#android", "#gaming", "#coding",
            "#programming", "#review", "#ai", "#software",
        ],
    },
    {
        "name": "Мотивация",
        "description": "Мотивация, вдохновение, достижения",
        "folder": "motivation",
        "hashtags": [
            "#мотивация", "#успех", "#цели", "#развитие", "#саморазвитие", "#психология",
            "#вдохновение", "#цитаты", "#историиуспеха", "#ментинг",
            "#motivation", "#success", "#goals", "#mindset", "#inspiration", "#quotes",
            "#productivity", "#habits", "#growth", "#hustle",
        ],
    },
]

# Минимум лайков для отбора популярных роликов
DEFAULT_MIN_LIKES = 10_000
# Минимум просмотров (от 500k)
DEFAULT_MIN_VIEWS = 500_000
# Длительность Shorts (сек)
MIN_DURATION = 10
MAX_DURATION = 120
