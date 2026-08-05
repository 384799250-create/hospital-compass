from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DemoHospital:
    """In-memory demo data only; it is not a directory of real hospitals."""

    name: str
    pinyin_name: str
    city: str
    specialties: tuple[str, ...]
    specialty_score: int | None
    capability_score: int | None
    geography_score: int | None
    source_date: date
    published: bool = True
    verified: bool = True
    demo_label: str = 'DEMO DATA'
    id: str = ''


TODAY = date.today()

DEMO_HOSPITALS = (
    DemoHospital(
        id='demo-1',
        name='示例市中心医院',
        pinyin_name='shilishizhongxinyiyuan',
        city='上海',
        specialties=('心血管内科',),
        specialty_score=100,
        capability_score=90,
        geography_score=100,
        source_date=TODAY - timedelta(days=10),
    ),
    DemoHospital(
        id='demo-2',
        name='示例浦东医院',
        pinyin_name='shilipudongyiyuan',
        city='上海',
        specialties=('心血管内科',),
        specialty_score=85,
        capability_score=85,
        geography_score=100,
        source_date=TODAY - timedelta(days=30),
    ),
    DemoHospital(
        id='demo-3',
        name='示例杭州医院',
        pinyin_name='shilihangzhouyiyuan',
        city='杭州',
        specialties=('心血管内科',),
        specialty_score=95,
        capability_score=95,
        geography_score=0,
        source_date=TODAY - timedelta(days=20),
    ),
    DemoHospital(
        id='demo-private',
        name='Unpublished demo hospital',
        pinyin_name='unpublisheddemohospital',
        city='Shanghai',
        specialties=(),
        specialty_score=None,
        capability_score=None,
        geography_score=None,
        source_date=TODAY,
        published=False,
    ),
)
