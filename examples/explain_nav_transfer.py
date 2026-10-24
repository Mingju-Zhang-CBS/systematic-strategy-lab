"""One funded transfer; accumulation NAV income must not be added twice."""
import numpy as np
from strategy_lab.real_research import rebalance_units

units=np.array([1000.,0,0,0,0]);prices=np.ones(5)*100
weights=np.array([0.,0.,1.,0.,0.])
new,fee,gross,_=rebalance_units(units,prices,weights,10)
assert abs(new@prices+fee-100000)<1e-7
assert abs(fee-.001*gross)<1e-7
ending=new@np.array([100.,100.,102.,100.,100.])
assert abs(ending-(100000-fee)*1.02)<1e-7
print(f"Initial G value: $100,000.00; two-leg gross: ${gross:,.2f}; fee: ${fee:,.2f}")
print(f"C units: {new[2]:,.6f}; after 2% accumulation NAV rise: ${ending:,.2f}; extra dividend: $0")
