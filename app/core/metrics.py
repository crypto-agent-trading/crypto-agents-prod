from prometheus_client import Counter, Gauge

orders_placed = Counter("cap_orders_placed", "Orders placed", ["symbol", "side", "mode"])
orders_filled = Counter("cap_orders_filled", "Orders filled", ["symbol", "side", "mode"])
orders_rejected = Counter("cap_orders_rejected", "Orders rejected", ["symbol", "side", "mode"])
positions_gauge = Gauge("cap_position", "Current position size", ["symbol", "mode"])
pnl_gauge = Gauge("cap_pnl", "Unrealized PnL", ["symbol", "mode"])
kill_switch = Gauge("cap_kill_switch", "Kill switch status (1=enabled,0=disabled)")
