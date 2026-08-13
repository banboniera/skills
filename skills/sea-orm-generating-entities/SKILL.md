---
name: sea-orm-generating-entities
description: Use when generating SeaORM 2.0 entities from a database, defining entity models and custom types, or adopting the entity-first schema-sync workflow
---

# SeaORM Entity Generation (2.0)

## Overview

Use `sea-orm-cli` to derive entity modules from MySQL, PostgreSQL, or SQLite schema. Entity-first projects define `#[sea_orm::model]`; schema sync creates missing objects. Keep Rust model, DB type, backend capabilities aligned.

## When to Use

- Existing DB tables need SeaORM entities.
- Entity needs non-default mapping, `ActiveEnum`, JSON, or typed wrapper.
- Additive development schema should follow entity definitions, not hand-written migrations.

Do not use schema sync for destructive production migrations: it does not drop tables, columns, or foreign keys.

## Choosing the Workflow

| Starting point | Use | Boundary |
| --- | --- | --- |
| Existing DB schema | CLI generation | Regeneration overwrites generated structure; preserve supported additions only |
| Hand-authored entities, additive development schema | Entity-first schema sync | Discovery-based, addition-only; not production migration replacement |
| Cross-backend model | Portable field types | PostgreSQL arrays/native enums intentionally require that backend |

## Using sea-orm-cli

Install 2.0 CLI, set `DATABASE_URL` in environment or project-root `.env`, then generate:

```shell
cargo install sea-orm-cli@^2.0

sea-orm-cli generate entity \
  --database-url postgres://user:password@localhost/bakery \
  --database-schema public \
  --output-dir ./src/entity \
  --entity-format dense
```

`-u`/`--database-url` defaults to `DATABASE_URL`; `-s`/`--database-schema` to `DATABASE_SCHEMA`. Schema is ignored for MySQL/SQLite; PostgreSQL defaults to `public`. Command help: `sea-orm-cli -h`, `sea-orm-cli generate -h`, `sea-orm-cli generate entity -h`.

| Need | Options |
| --- | --- |
| Output/diagnostics | `-o, --output-dir`, `-v, --verbose`, `-l, --lib` (`lib.rs`, not `mod.rs`) |
| Tables | `--include-hidden-tables` for `_` prefix; `--ignore-tables` (default `seaql_migrations`) |
| Layout | `--entity-format dense` (2.0), `compact` (1.0), `expanded` (0.x), `frontend`; legacy `--compact-format`, `--expanded-format` documented |
| Annotations | `--model-extra-derives`, `--model-extra-attributes`, `--enum-extra-derives`, `--enum-extra-attributes`, `--column-extra-derives` |
| Serialization/time | `--with-serde none|serialize|deserialize|both`, `--serde-skip-deserializing-primary-key`, `--serde-skip-hidden-column`, `--date-time-crate chrono|time` |
| Modules/behavior | `--with-prelude all|none|all-allow-unused-imports`, `--impl-active-model-behavior`, `--seaography` |
| Discovery/preservation | `--max-connections`, `--acquire_timeout` (seconds), `--big-integer-type i32|i64` for SQLite `bigint`, `--experimental-preserve-user-modifications` (`--preserve-user-modifications` deprecated) |
| Artifact | `--er-diagram` writes `entities.mermaid` |

Before compiling consumer, inspect requested root (`lib.rs` with `--lib`, otherwise `mod.rs`), declared entity modules, included hidden tables. This separates incomplete generation from crate integration failure. Preservation retains supported manual `Model`/`Relation` additions and `ActiveModelBehavior` impls; not a general merge tool.

## Entity Structure

Dense 2.0 uses `#[sea_orm::model]` with `DeriveEntityModel`, generating `Entity`, `Column`, `PrimaryKey`, and type-specific `COLUMN` constants for compile-time query checks.

```rust
use sea_orm::entity::prelude::*;

#[sea_orm::model]
#[derive(Clone, Debug, PartialEq, Eq, DeriveEntityModel)]
#[sea_orm(table_name = "cake")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    pub name: String,
    #[sea_orm(has_one)]
    pub fruit: Option<super::fruit::Entity>,
    #[sea_orm(has_many, via = "cake_filling")]
    pub fillings: Vec<super::filling::Entity>,
}

impl ActiveModelBehavior for ActiveModel {}
```

Keep empty `ActiveModelBehavior`. Set `schema_name` with `table_name` if needed. Fields default to snake_case; override with model `rename_all` or field `#[sea_orm(column_name = "...")]`.

```rust
#[sea_orm(column_type = "Decimal(Some((16, 4)))")]
pub price: Decimal,

#[sea_orm(column_type = "Text", default_value = "Sam", unique, indexed, nullable)]
pub name: Option<String>,
```

Usually infer `column_type`; an `Option<T>` override also needs `nullable`. Other attributes: `default_value`, `unique`, `indexed`, `ignore`, `select_as`, `save_as`; `select_as = "text", save_as = "citext"` supports PostgreSQL `citext`. Reuse `unique_key = "name"` on fields for composite unique key. Primary key auto-increments unless `auto_increment = false`; multiple `primary_key` fields make composite key (max arity 12).

## Column Types

SeaORM infers `ColumnType` from Rust type:

| Rust type | `ColumnType` | Backend note |
| --- | --- | --- |
| `String` | `Char`/`String` | `char`/`varchar` |
| `i8`/`i16`/`i32`/`i64` | `TinyInteger`/`SmallInteger`/`Integer`/`BigInteger` | portable signed |
| `u8`/`u16`/`u32`/`u64` | `TinyUnsigned`/`SmallUnsigned`/`Unsigned`/`BigUnsigned` | PostgreSQL has no native unsigned; SQLite cannot encode `u64` |
| `f32`/`f64`/`bool`/`Vec<u8>` | `Float`/`Double`/`Boolean`/`Binary` | blob/bytea for `Vec<u8>` |
| `Date`, `Time`, `DateTime` or `time` equivalents | `Date`, `Time`, `DateTime` | CLI `--date-time-crate chrono|time` |
| `DateTimeLocal`/`DateTimeUtc` | `Timestamp` | PostgreSQL N/A; use aliases below for zone-aware timestamps |
| `DateTimeWithTimeZone`/`TimeDateTimeWithTimeZone` | `TimestampWithTimeZone` | PostgreSQL `timestamp with time zone`; SQLite text |
| `Uuid`, `Json`, `Decimal` | `Uuid`, `Json`, `Decimal` | representations differ |

Override precision/representation as needed:

```rust
#[sea_orm(column_type = "Text")]
pub name: String,
#[sea_orm(column_type = "Decimal(Some((16, 4)))")]
pub price: Decimal,
```

Structured JSON: derive `Serialize`, `Deserialize`, `FromJsonQueryResult`; use `JsonBinary` when optional field requires PostgreSQL `jsonb`.

```rust
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, FromJsonQueryResult)]
pub struct Metadata {
    pub label: String,
}

pub metadata: Option<Metadata>,
```

`Vec` columns are PostgreSQL-only arrays; portable arrays use JSON wrapper. `PgVector` is PostgreSQL-only and needs `postgres-vector`; `IpNetwork` needs `with-ipnetwork`. 2.0 `ChronoUnixTimestamp`, `ChronoUnixTimestampMillis`, `TimeUnixTimestamp`, `TimeUnixTimestampMillis` store datetime as `BigInteger` (`i64`).

### Backend Boundary

Choose DB representation before public entity API. PostgreSQL `Vec<T>`, `PgVector`, native enums are deliberate PostgreSQL dependencies; SQLite differs; MySQL native enums are column-local. For PostgreSQL+SQLite, use serializable JSON collections and string-backed `DeriveActiveEnum` when native enforcement unnecessary. For PostgreSQL-only native enum, create type before table in migrations.

## Enumeration

`DeriveActiveEnum` maps Rust enum to DB string, integer, or native enum: specify Rust storage type, DB type, every persisted value.

```rust
use sea_orm::entity::prelude::*;

#[derive(Debug, Clone, PartialEq, Eq, EnumIter, DeriveActiveEnum)]
#[sea_orm(rs_type = "String", db_type = "String(StringLen::N(1))", enum_name = "category")]
pub enum Category {
    #[sea_orm(string_value = "B")]
    Big,
    #[sea_orm(string_value = "S")]
    Small,
}

#[sea_orm::model]
#[derive(Clone, Debug, PartialEq, Eq, DeriveEntityModel)]
#[sea_orm(table_name = "active_enum")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    pub category: Category,
    pub category_opt: Option<Category>,
}

impl ActiveModelBehavior for ActiveModel {}
```

Strings: `rename_all` or `string_value`; integers: `num_value` or discriminants (`Black = 0`). Client-side string enum: `DeriveValueType`, `FromStr`, `Display` (or `from_str`/`to_str`). Native enum: `db_type = "Enum"`, `enum_name`; MySQL enums cannot be reused. PostgreSQL requires `CREATE TYPE` before table; derive migration statement:

```rust
let schema = Schema::new(DbBackend::Postgres);
manager
    .create_type(schema.create_enum_from_active_enum::<Tea>().expect("Postgres only"))
    .await?;
```

SQLite maps enums to strings.

## New Type

Use `DeriveValueType` for supported scalar; it implements `From<T> for Value`, `TryGetable`, `ValueType`, `Nullable`.

```rust
use sea_orm::entity::prelude::*;

#[derive(Clone, Debug, PartialEq, Eq, DeriveValueType)]
pub struct AccountId(pub i64);

#[sea_orm::model]
#[derive(Clone, Debug, PartialEq, Eq, DeriveEntityModel)]
#[sea_orm(table_name = "account")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: AccountId,
}

impl ActiveModelBehavior for ActiveModel {}
```

Since 2.0, wrapped `i8`, `i16`, `i32`, `i64`, `u8`, `u16`, `u32`, `u64` can be primary keys. `DeriveValueType` wrapper around `Vec<T>` is PostgreSQL-only; portable vectors/arbitrary structures should derive `Serialize`, `Deserialize`, `FromJsonQueryResult` for JSON backing. Since 2.0, it supports string-like structs: implement `Display`/`FromStr`; optionally set `#[sea_orm(value_type = "String", column_type = "Text")]`.

## Entity First Workflow

Entity-first hand-writes entities, then syncs tables/FKs. Enable 2.0 features:

```toml
[dependencies]
sea-orm = { version = "2.0", features = ["schema-sync", "entity-registry"] }
```

Connect, obtain registry for crate entity modules, sync. Registry begins with Cargo.toml crate name:

```rust
let db = &Database::connect(db_url).await?;
db.get_schema_registry("my_crate::entity::*").sync(db).await?;

// Or derive the caller crate name:
db.get_schema_registry(module_path!().split("::").next().unwrap())
    .sync(db)
    .await?;
```

`entity-registry` is optional inventory convenience; explicit registration:

```rust
db.get_schema_builder()
    .register(comment::Entity)
    .register(post::Entity)
    .sync(db)
    .await?;
```

`sync` discovers live schema, idempotently creates missing tables, columns, keys, indexes, and orders related tables from dependency graph. New non-null field needs `default_value` or `default_expr`; SQLite cannot use documented `default_expr = "Expr::current_timestamp()"` case. Rename DB column with `#[sea_orm(renamed_from = "old_name")]`; `column_name` only changes Rust-to-existing mapping.

Schema sync avoids destructive table, column, FK changes; dropping index is exception. SQLite cannot add FK after table exists, though client-side relational queries work. Because every app start performs discovery, enable `schema-sync` only in appropriate build profiles.

In migrations use `SchemaBuilder::apply`, not `sync`: bookkeeping prevents repeat application. Preserve initial entities in submodule (time capsule) so migrations remain sequentially reproducible.

```rust
#[async_trait::async_trait]
impl MigrationTrait for Migration {
    async fn up(&self, manager: &SchemaManager) -> Result<(), DbErr> {
        let db = manager.get_connection();
        db.get_schema_builder()
            .register(note::Entity)
            .apply(db)
            .await
    }
}
```

## Reference

- https://www.sea-ql.org/SeaORM/docs/generate-entity/sea-orm-cli/
- https://www.sea-ql.org/SeaORM/docs/generate-entity/entity-format/
- https://www.sea-ql.org/SeaORM/docs/generate-entity/column-types/
- https://www.sea-ql.org/SeaORM/docs/generate-entity/enumeration/
- https://www.sea-ql.org/SeaORM/docs/generate-entity/newtype/
- https://www.sea-ql.org/SeaORM/docs/generate-entity/entity-first/
