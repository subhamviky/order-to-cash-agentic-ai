# The P0 Dockerfile serves on port 8000 (the A2C template's default is 8080).
container_port = 8000

# The demonstration landscape's scenario buys goods on every run (3 printers, 2 to 21 scanners) and would empty the
# seeded stock after about 16 runs: top each SKU up to its catalog level once a day. Leave this false where stock is real.
daily_restock = true
