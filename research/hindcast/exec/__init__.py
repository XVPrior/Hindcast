"""Live execution against exchange testnets/mainnet.

Anything in this package can talk to a real exchange API. Backtesting
code in hindcast.backtest must NOT import from here — it would let
strategies accidentally reach the network during a backtest.
"""
