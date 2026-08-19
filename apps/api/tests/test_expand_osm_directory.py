import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.expand_osm_directory import _split_bbox


def test_split_bbox_covers_parent_bbox_without_oversized_tiles():
    tiles = _split_bbox((0.0, 0.0, 2.2, 3.1), max_span=1.0)

    assert len(tiles) == 12
    assert tiles[0] == (0.0, 0.0, 1.0, 1.0)
    assert tiles[-1] == (2.0, 3.0, 2.2, 3.1)
    assert min(tile[0] for tile in tiles) == 0.0
    assert max(tile[2] for tile in tiles) == 2.2
    assert min(tile[1] for tile in tiles) == 0.0
    assert max(tile[3] for tile in tiles) == 3.1
