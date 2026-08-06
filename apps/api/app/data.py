from dataclasses import dataclass
from datetime import date
from typing import Mapping


# This draft file is deliberately not loaded into the public demo dataset.
PILOT_DRAFT_CSV_PATH = 'app/data/pilot_hospitals.csv'


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


def verified_row_to_hospital(row: Mapping[str, str]) -> DemoHospital:
    """Adapt one validated public-list row to the matching data shape."""
    return DemoHospital(
        id=row['id'],
        name=row['name'],
        pinyin_name=row['id'],
        city=row['city'],
        specialties=tuple(part.strip() for part in row['specialties'].split('|') if part.strip()),
        specialty_score=None,
        capability_score=None,
        geography_score=None,
        source_date=date.fromisoformat(row['source_date']),
        published=row['published'] == 'true',
        verified=row['verified'] == 'true',
        demo_label='已核验公开信息',
    )


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
        source_date=date(2026, 7, 26),
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
        source_date=date(2026, 7, 6),
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
        source_date=date(2026, 7, 16),
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
        source_date=date(2026, 8, 5),
        published=False,
    ),
)
