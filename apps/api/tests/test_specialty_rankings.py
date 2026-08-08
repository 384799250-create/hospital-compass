from app.specialty_rankings import SpecialtyRankingEvidence, rank_to_score


def test_specialty_ranking_evidence_normalizes_identity_fields_and_keeps_provenance():
    evidence = SpecialtyRankingEvidence(
        hospital='  Beijing   Union Hospital  ',
        city='  Beijing  ',
        specialty='  Cardiology  ',
        rank=1,
        year=2025,
        source=' National specialty ranking / published edition ',
    )

    assert evidence.hospital == 'Beijing Union Hospital'
    assert evidence.city == 'Beijing'
    assert evidence.specialty == 'Cardiology'
    assert evidence.rank == 1
    assert evidence.score == 10.0
    assert evidence.year == 2025
    assert evidence.source == ' National specialty ranking / published edition '
    assert evidence.verification_status == '待核验'


def test_rank_to_score_descends_by_rank_and_bottoms_out_at_zero():
    assert rank_to_score(1) == 10.0
    assert rank_to_score(10) == 1.0
    assert rank_to_score(11) == 0.0


def test_missing_rank_uses_the_unranked_score_fallback():
    evidence = SpecialtyRankingEvidence(
        hospital='Example Hospital',
        city='Shanghai',
        specialty='Oncology',
        rank=None,
        year=2024,
        source='https://example.org/ranking',
    )

    assert evidence.score == 0.0
    assert rank_to_score(None) == 0.0
