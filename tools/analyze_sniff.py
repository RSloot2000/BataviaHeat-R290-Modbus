"""Quick analysis of tablet sniffer JSON output."""
import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "data/tablet_sniff_20260317_145904.json"
with open(path, encoding="utf-8") as f:
    data = json.load(f)

print("=== Invalid frames (first 20) ===")
for fr in data.get("invalid_frames", [])[:20]:
    h = fr["hex"]
    print(f"  len={fr['length']:2d}  hex={h}")

print()
print("=== All valid requests ===")
for r in data.get("all_requests", [])[:60]:
    addr = r.get("start_addr", "?")
    count = r.get("count", "?")
    print(f"  t={r['timestamp']:7.3f}  slave={r['slave_id']}  FC=0x{r['fc']:02X}  start={addr}  count={count}  raw={r['raw_hex']}")
