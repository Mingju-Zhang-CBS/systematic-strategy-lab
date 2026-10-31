import pandas as pd
import pytest
from strategy_lab.intraday.evidence import (recover_quote_clusters, evaluate_action_evidence,
                                           select_quote_sources, resolve_dated_lots)


def clocks():
    c = pd.DataFrame({'asset': ['SYNTH']*3, 'quote_time': ['2020-01-02 15:00:01.123457Z']*3,
                      'bid': [100.]*3, 'ask': [100.01]*3,
                      'bid_size': [200, 300, 400], 'ask_size': [500]*3})
    f = pd.DataFrame({'asset': ['SYNTH']*3,
                      'sip_time': ['2020-01-02 15:00:01.123456Z']*2+['2020-01-02 15:00:01.123457Z'],
                      'nano': [600, 800, 100], 'bid': [100.]*3, 'ask': [100.01]*3,
                      'bid_lots': [2, 3, 4], 'ask_lots': [5]*3,
                      'lot_size': [100]*3, 'condition': ['R']*3,
                      'source': ['SYNTH_FEED']*3, 'sequence': [10, 11, 12]})
    return c, f


def test_fine_clock_and_lot_units_restore_order_without_coarse_substitution():
    c, f = clocks(); out, audit = recover_quote_clusters(c, f.iloc[::-1])
    assert audit.status.to_list() == ['matched_fine_clock']
    assert out.sequence.to_list() == [10, 11, 12]
    assert out.bid_size.to_list() == [200, 300, 400]
    assert out.quote_time.iloc[0] == pd.Timestamp('2020-01-02 15:00:01.123456600Z')
    assert c.quote_time.iloc[0] == '2020-01-02 15:00:01.123457Z'


@pytest.mark.parametrize('change,status', [
    ('quantity', 'tuple_coverage_mismatch'), ('missing', 'tuple_coverage_mismatch'),
    ('half', 'half_quantum_tie'), ('source', 'sequence_scope_ambiguous'),
    ('condition', 'quote_condition_unverified'),
    ('sequence', 'clock_sequence_disagreement')])
def test_conflicts_are_retained_not_resolved_by_price_or_depth(change, status):
    c, f = clocks()
    if change == 'quantity': f.loc[0, 'lot_size'] = 10
    if change == 'missing': f = f.iloc[1:]
    if change == 'half': f.loc[0, 'nano'] = 500
    if change == 'source': f.loc[0, 'source'] = 'OTHER'
    if change == 'condition': f.loc[0, 'condition'] = 'N'
    if change == 'sequence': f.loc[0, 'sequence'] = 14
    out, audit = recover_quote_clusters(c, f)
    # Half-quantum rounding can map to either adjacent bin; neither is admitted.
    assert out.empty
    if change == 'half':
        assert audit.status.iloc[0] in [status, 'tuple_coverage_mismatch']
    else:
        assert audit.status.iloc[0] == status


def test_invalid_nano_rejected_at_boundary():
    c, f = clocks(); f.loc[0, 'nano'] = 1000
    with pytest.raises(ValueError): recover_quote_clusters(c, f)


def test_naive_quote_clock_is_not_assumed_utc():
    c, f = clocks(); f['sip_time'] = pd.to_datetime(f.sip_time).dt.tz_localize(None)
    with pytest.raises(ValueError, match='timezone'): recover_quote_clusters(c, f)


def test_submicrosecond_window_boundary_does_not_make_early_quote_executable():
    c, f = clocks(); recovered, _ = recover_quote_clusters(c, f)
    arrival = pd.Timestamp('2020-01-02 15:00:01.123457Z')
    eligible = recovered.loc[recovered.quote_time >= arrival]
    assert eligible.sequence.to_list() == [12]
    assert (recovered.quote_time < arrival).sum() == 2


def test_future_clusters_do_not_change_past_recovery():
    c, f = clocks(); expected, _ = recover_quote_clusters(c, f)
    later_c, later_f = c.copy(), f.copy()
    later_c['quote_time'] = pd.to_datetime(later_c.quote_time)+pd.Timedelta(days=1)
    later_f['sip_time'] = pd.to_datetime(later_f.sip_time)+pd.Timedelta(days=1)
    actual, _ = recover_quote_clusters(pd.concat([c, later_c]), pd.concat([f, later_f]))
    pd.testing.assert_frame_equal(expected, actual.iloc[:3].reset_index(drop=True))


def evidence():
    return pd.DataFrame([{'evidence_id': 'invented', 'kind': 'gross_cash_amount',
                         'identity_verified': True, 'amount_verified': True,
                         'currency': 'USD', 'unit': 'gross_per_share',
                         'clock_basis': 'exchange_release_timestamp', 'source_sha256': 'a'*64,
                         'published_at': '2020-01-02T08:00:00+08:00',
                         'decision_at': '2020-01-02T14:30:00Z'}])


def test_primary_amount_release_is_compared_across_timezones():
    out = evaluate_action_evidence(evidence())
    assert out.strict_usable.all()
    assert out.published_at.iloc[0] == pd.Timestamp('2020-01-02T00:00:00Z')


def test_naive_publication_clock_is_not_assumed_utc():
    e = evidence(); e.loc[0, 'published_at'] = '2020-01-02 08:00:00'
    with pytest.raises(ValueError, match='timezone'): evaluate_action_evidence(e)


@pytest.mark.parametrize('field,value,status', [
    ('kind', 'distribution_schedule', 'schedule_or_other_fact_not_amount'),
    ('clock_basis', 'document_date_only', 'publication_clock_not_verified'),
    ('published_at', '2020-01-02T14:30:00Z', 'not_known_before_decision'),
    ('published_at', None, 'not_known_before_decision'),
    ('amount_verified', False, 'identity_or_amount_unverified'),
    ('unit', 'net_after_withholding', 'currency_or_unit_mismatch')])
def test_incomplete_or_late_evidence_cannot_unlock_action(field, value, status):
    e = evidence(); e.loc[0, field] = value
    out = evaluate_action_evidence(e)
    assert not out.strict_usable.any()
    assert out.evidence_status.iloc[0] == status


@pytest.mark.parametrize('source,indicator,date,accepted', [
    ('N', '4', '2016-01-04', True), ('N', '0', '2016-01-04', False),
    ('N', '2', '2016-01-04', False), ('C', '1', '2017-10-27', True),
    ('C', 'G', '2017-10-27', False), ('C', 'G', '2017-10-30', True),
    ('C', '1', '2017-10-30', False), ('C', 'U', '2017-10-30', False)])
def test_only_dated_self_nbbo_cqm_can_supply_both_sides(source, indicator, date, accepted):
    _, f = clocks(); f = f.iloc[:1].copy()
    f['source'] = source; f['session'] = date
    f['raw_file'] = 'CQM'; f['natbbo_ind'] = indicator
    chosen, audit = select_quote_sources(f)
    assert bool(len(chosen)) == accepted
    assert audit.source_status.iloc[0] == ('source_eligible' if accepted else 'not_self_nbbo')


def test_cross_file_duplicate_does_not_add_displayed_capacity():
    _, f = clocks(); f['source'] = 'N'; f['session'] = '2020-01-02'
    f['raw_file'] = 'NBBO'; f['natbbo_ind'] = '4'
    copy = f.copy(); copy['raw_file'] = 'CQM'
    chosen, audit = select_quote_sources(pd.concat([f, copy]))
    assert len(audit) == 6 and len(chosen) == 3
    assert chosen.bid_lots.sum() == f.bid_lots.sum()


def test_conflicting_cross_file_sequence_is_quarantined_without_file_priority():
    _, f = clocks(); f = f.iloc[:1].copy()
    f['source'] = 'N'; f['session'] = '2020-01-02'
    f['raw_file'] = 'NBBO'; f['natbbo_ind'] = '4'
    copy = f.copy(); copy['raw_file'] = 'CQM'; copy['bid_lots'] = 100
    chosen, audit = select_quote_sources(pd.concat([f, copy]))
    assert chosen.empty
    assert audit.source_status.eq('conflicting_sequence_payload').all()


def test_exact_legacy_symbol_resolves_units_without_prefix_or_cross_date_fill():
    m = pd.DataFrame({'symbol_15': ['SYNTH', 'SYNTHX', 'OTHER'],
                      'sym_root': [None, None, None], 'sym_suffix': [None]*3,
                      'round_lot': [100, 10, 50]})
    result = resolve_dated_lots(m, ['SYNTH', 'MISSING'])
    assert result.to_dict('records') == [{'asset': 'SYNTH', 'lot_size': 100}]


def test_conflicting_lot_identity_does_not_choose_a_convenient_unit():
    m = pd.DataFrame({'symbol_15': ['SYNTH', 'SYNTH'], 'sym_root': [None, 'SYNTH'],
                      'sym_suffix': [None, None], 'round_lot': [100, 10]})
    assert resolve_dated_lots(m, ['SYNTH']).empty


def test_future_source_perturbation_does_not_change_past_eligible_quotes():
    _, f = clocks(); f['source'] = 'N'; f['session'] = '2020-01-02'
    f['raw_file'] = 'CQM'; f['natbbo_ind'] = '4'
    expected, _ = select_quote_sources(f)
    later = f.copy(); later['session'] = '2020-01-03'; later['bid_lots'] = 9999
    actual, _ = select_quote_sources(pd.concat([f, later]))
    pd.testing.assert_frame_equal(expected, actual.iloc[:3].reset_index(drop=True))


def test_minute_resolution_release_uses_conservative_end_before_decision():
    e = evidence()
    listed = pd.Timestamp('2020-01-02T14:29:00Z')
    e['published_at'] = listed + pd.Timedelta(minutes=1)
    # A release somewhere in the preceding minute cannot be asserted strictly
    # earlier than the decision when its conservative upper bound equals it.
    assert not evaluate_action_evidence(e).strict_usable.any()
    e['decision_at'] = '2020-01-02T14:30:01Z'
    assert evaluate_action_evidence(e).strict_usable.all()
