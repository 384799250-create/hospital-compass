"""Parser for the public 丁香园医院汇 directory pages."""

from html.parser import HTMLParser
import re


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.link = ''
        self.rows: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = dict(attrs).get('class') or ''
        self.stack.append((tag, classes))
        if tag == 'div' and 'tr' in classes.split() and self.row is None:
            self.row, self.link = [], ''
        elif tag == 'div' and 'td' in classes.split() and self.row is not None and self.cell is None:
            self.cell = []
        elif tag == 'a' and self.row is not None:
            self.link = dict(attrs).get('href') or self.link

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return
        start_tag, classes = self.stack.pop()
        if start_tag != tag:
            return
        if tag == 'div' and 'td' in classes.split() and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'div' and 'tr' in classes.split() and self.row is not None:
            if self.link and self.row:
                self.rows.append(_row(self.link, self.row))
            self.row = None
            self.link = ''


def parse_hospital_list(html: str) -> list[dict[str, str]]:
    parser = _Parser()
    parser.feed(html)
    return parser.rows


def _row(link: str, cells: list[str]) -> dict[str, str]:
    match = re.search(r'/hospital/(\d+)', link)
    if not match or len(cells) < 5:
        return {}
    area = cells[1] if len(cells) > 1 else ''
    province, _, city = area.partition('·')
    province = _province_name(province.strip())
    return {
        'id': f'dxy-{match.group(1)}',
        'name': cells[0],
        'province': province,
        'city': city.strip(),
        'address': '',
        'tier': cells[4] if len(cells) > 4 else '',
        'nature': cells[2] if len(cells) > 2 else '',
        'hospital_type': cells[3] if len(cells) > 3 else '',
        'source_url': f'https://y.dxy.cn/hospital/{match.group(1)}',
    }


def _province_name(value: str) -> str:
    if value in {'北京', '上海', '天津', '重庆'}:
        return f'{value}市'
    if value.endswith(('省', '自治区', '特别行政区')):
        return value
    return f'{value}省' if value else ''
