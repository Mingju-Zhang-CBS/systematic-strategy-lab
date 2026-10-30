"""Fixed hypothetical admission buffers; no calibrated margin or gap bound."""
import numpy as np

OUTAGE_SESSIONS = 20
ADVERSE_FRACTION = .10
RESERVE_RATE = .40
CASH_BUFFER_FRACTION = .10


def cash_envelope(quantity, price_basis, multipliers, unit_cost, cash, announced_rate, extra_fee=0.):
    """Consume normalized lagged arrays; no credit for expected liquidation.

    Absolute leg exposure charges both sides of a spread. Reserve is encumbered
    cash, while hypothetical VM loss and fees reduce cash; do not debit it twice.
    """
    units=np.abs(quantity)
    gross=float(np.sum(units*multipliers*price_basis))
    loss=ADVERSE_FRACTION*gross
    reserve=max(RESERVE_RATE,announced_rate)*(1+ADVERSE_FRACTION)*gross
    fees=float(2*np.sum(units*unit_cost)+extra_fee)
    buffer=CASH_BUFFER_FRACTION*max(0.,cash)
    required=loss+reserve+fees+buffer
    return dict(available_cash=float(cash),gross=gross,adverse_loss=loss,
                stressed_reserve=reserve,round_trip_fees=fees,transition_fee_surcharge=float(extra_fee),cash_buffer=buffer,
                required_cash=required,cash_slack=float(cash-required),cash_admitted=required<=cash)


def transition_surcharge(previous, reduced, target, unit_cost):
    """Cover planned reductions, additions and eventual target liquidation.

    Keep the conservative reversal allowance while also covering same-direction
    retirement/reentry. Normalized inventory and cost arrays enter from engine.
    """
    envelope=np.maximum(np.abs(previous),np.abs(target))
    reversal=np.where(previous*target<0,np.minimum(np.abs(previous),np.abs(target)),0)
    route=np.abs(reduced-previous)+np.abs(target-reduced)+np.abs(target)
    extra=np.maximum(reversal,np.maximum(0,route-2*envelope))
    return float(np.sum(extra*unit_cost))
