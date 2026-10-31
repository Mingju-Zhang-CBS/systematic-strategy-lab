"""Invented clock and publication cases; no vendor records or realized returns."""
from pathlib import Path
import argparse
import hashlib
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from strategy_lab.intraday.evidence import recover_quote_clusters, evaluate_action_evidence
from strategy_lab.intraday import evidence as evidence_module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('reports/intraday-evidence-fixture'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    coarse = pd.DataFrame({'asset': ['SYNTH']*3, 'quote_time': ['2020-01-02 15:00:01.123457Z']*3,
                           'bid': [100.]*3, 'ask': [100.01]*3,
                           'bid_size': [200, 300, 400], 'ask_size': [500]*3})
    fine = pd.DataFrame({'asset': ['SYNTH']*3,
                         'sip_time': ['2020-01-02 15:00:01.123456Z']*2+['2020-01-02 15:00:01.123457Z'],
                         'nano': [600, 800, 100], 'bid': [100.]*3, 'ask': [100.01]*3,
                         'bid_lots': [2, 3, 4], 'ask_lots': [5]*3,
                         'lot_size': [100]*3, 'condition': ['R']*3,
                         'source': ['INVENTED']*3, 'sequence': [10, 11, 12]})
    recovered, audit = recover_quote_clusters(coarse, fine)
    rows = []
    for key, kind, basis, published in [
        ('Verified amount', 'gross_cash_amount', 'exchange_release_timestamp', '2020-01-02T08:00:00+08:00'),
        ('Schedule only', 'distribution_schedule', 'exchange_release_timestamp', '2020-01-01T00:00:00Z'),
        ('Printed date only', 'gross_cash_amount', 'document_date_only', '2020-01-01T23:59:59+08:00'),
        ('Released at decision', 'gross_cash_amount', 'exchange_release_timestamp', '2020-01-02T14:30:00Z')]:
        rows.append({'evidence_id': key, 'kind': kind, 'clock_basis': basis, 'published_at': published,
                     'decision_at': '2020-01-02T14:30:00Z', 'identity_verified': True,
                     'amount_verified': True, 'currency': 'USD', 'unit': 'gross_per_share',
                     'source_sha256': hashlib.sha256(key.encode()).hexdigest()})
    publication = evaluate_action_evidence(pd.DataFrame(rows))
    for name, frame in [('coarse', coarse), ('fine', fine), ('recovered', recovered),
                        ('cluster-audit', audit), ('publication', publication)]:
        frame.to_csv(args.output/f'{name}.csv', index=False)
    plt.rcParams.update({'figure.facecolor': '#FAF9F5', 'axes.facecolor': '#FAF9F5',
                         'text.color': '#101928', 'axes.spines.top': False,
                         'axes.spines.right': False, 'font.size': 10})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout='constrained')
    ax = axes[0]
    fine_x = [600, 800, 1100]
    ax.scatter(fine_x, [0]*3, s=85, color='#36B3A8', zorder=3)
    ax.scatter([1000], [1], s=85, color='#101928', zorder=3)
    for x, seq in zip(fine_x, [10, 11, 12]):
        ax.annotate(f'message {seq}', (x, 0), xytext=(0, -26), textcoords='offset points', ha='center', fontsize=9)
        ax.plot([x, 1000], [0, 1], color='#AAB8C4', lw=1)
    ax.axvline(1000, color='#CB7C58', ls='--', label='Example arrival')
    ax.set(xlim=(400, 1350), ylim=(-.45, 1.4), yticks=[0, 1],
           yticklabels=['Fine SIP clock', 'Rounded microsecond'],
           xlabel='Nanoseconds after an invented microsecond anchor',
           title='Rounding can merge distinct messages')
    ax.legend(loc='upper left', fontsize=9)
    ax = axes[1]
    labels = publication.evidence_id.to_list()
    ax.barh(labels[::-1], publication.strict_usable.astype(int).to_numpy()[::-1],
            color=['#36B3A8' if x else '#AAB8C4' for x in publication.strict_usable.to_list()[::-1]])
    ax.set(xlim=(0, 1.2), xticks=[0, 1], xticklabels=['Blocked', 'Admitted'],
           title='An amount and a release clock are separate facts')
    fig.suptitle('Source evidence before a trading claim | invented known-answer cases', fontsize=14)
    fig.savefig(args.output/'evidence_clocks.png', dpi=170); plt.close(fig)
    (args.output/'REPORT.md').write_text('''# Evidence Before Admission

All clocks, quantities, securities and publication examples here are **invented**.

![Clock and publication checks](evidence_clocks.png)

Three messages at offsets 600, 800 and 1,100 ns collapse to one microsecond label.
The original SIP remainder restores their order only after exact quote/quantity
matching and documented lot conversion. At the illustrated 1,000 ns arrival,
the first two messages are too early; the third is eligible. A same-time label
cannot justify picking the largest displayed quantity. Half-quantum ties,
missing tuples and conflicting sequence scopes remain quarantined.

The publication examples distinguish an actual amount release, a calendar,
a printed document date and a release at the decision. Only the verified earlier
amount passes. These inputs are analyst attestations exercised as a known-answer
test; the function does not authenticate a document or prove feed availability.

[Methods](../../docs/INTRADAY_EVIDENCE.md) · [Tests](../../tests/test_intraday_evidence.py)
''', encoding='utf-8')
    implementation = Path(evidence_module.__file__)
    (args.output/'run.json').write_text(json.dumps({'data': 'invented known-answer fixtures',
        'implementation_sha256': hashlib.sha256(implementation.read_bytes()).hexdigest(),
        'cluster_status': audit.status.to_list(), 'admitted_publication_cases': int(publication.strict_usable.sum()),
        'strategy_parameters_changed': False}, indent=2))
    print('Invented source-evidence report written; no market performance reported.')


if __name__ == '__main__': main()
