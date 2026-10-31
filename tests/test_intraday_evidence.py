import pandas as pd
import pytest
from strategy_lab.intraday.evidence import recover_quote_clusters, evaluate_action_evidence


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
