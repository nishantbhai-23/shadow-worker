from sqlalchemy import BigInteger, Integer

# Postgres BIGINT/BIGSERIAL, but plain INTEGER under SQLite -- SQLite's rowid-alias
# autoincrement magic for primary keys only kicks in for INTEGER affinity, not BIGINT,
# so a real BigInteger primary key silently fails to auto-generate under the SQLite
# tests use. SQLite's storage isn't actually 32-bit-limited either way.
BIGINT_PK = BigInteger().with_variant(Integer(), "sqlite")
