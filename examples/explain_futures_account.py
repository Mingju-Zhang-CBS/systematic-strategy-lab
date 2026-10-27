"""Invented WTI pair: variation margin, two-sided friction and model collateral."""

capital, multiplier, tick, commission = 1_000_000, 1000, .01, 2.50
near_entry, far_entry = 70, 72
near_close, far_close = 71, 72.40
entry_cost = 2 * (commission + tick * multiplier)
variation_margin = multiplier * ((near_close-near_entry) - (far_close-far_entry))
close_cost = entry_cost
reserve_at_entry = .10 * multiplier * (abs(near_entry)+abs(far_entry))
final_equity = capital-entry_cost+variation_margin-close_cost
assert abs(variation_margin-600) < 1e-8
assert reserve_at_entry == 14200
assert abs(final_equity-1_000_550) < 1e-8
print(f"SYNTHETIC | entry costs ${entry_cost:.2f}; variation margin ${variation_margin:.2f}; close costs ${close_cost:.2f}")
print(f"Model reserve ${reserve_at_entry:.2f} encumbers cash, not an extra expense; final equity ${final_equity:.2f}")
