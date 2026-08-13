---
name: sea-orm-migration
description: Use when an agent needs to create, write, run, roll back, inspect, or seed SeaORM 2.0 database migrations.
---

# SeaORM 2.0 Migrations

SeaORM migrations are ordered `MigrationTrait` implementations. `Migrator` records applied files in `seaql_migrations` by default, runs `up` chronologically, and uses matching `down` to revert. Prefer SeaQuery via `SchemaManager` for portable DDL; raw SQL only for intentional database-specific behavior.

## When to Use

- Initialize a migration crate or add it to an app workspace.
- Create or register schema migrations.
- Apply, roll back, reset, refresh, or inspect migrations.
- Add versioned migration seed data.

## Setting Up Migration

Install 2.0 CLI, create default `migration` crate, or choose directory:

```shell
cargo install sea-orm-cli@^2.0
sea-orm-cli migrate init
sea-orm-cli migrate init -d ./other/migration/dir
```

Generated crate: `src/lib.rs` library-facing `Migrator`, `src/main.rs` standalone CLI, initial migration. Keep it separate in Cargo workspace when practical. Configure `sea-orm-migration` and Tokio; enable runtime plus matching database backend for CLI:

```toml
# migration/Cargo.toml
[dependencies]
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }

[dependencies.sea-orm-migration]
version = "2.0"
features = ["runtime-tokio-native-tls", "sqlx-postgres"]
```

Make crate workspace member; app depends on it when running migrations at startup:

```toml
# Cargo.toml
[workspace]
members = [".", "migration"]

[dependencies]
migration = { path = "migration" }
sea-orm = { version = "2.0.0", features = ["runtime-tokio-native-tls", "sqlx-postgres"] }
```

Migration record table is automatic. Override only when required:

```rust
#[async_trait::async_trait]
impl MigratorTrait for Migrator {
    fn migration_table_name() -> sea_orm::DynIden {
        "app_migrations".into_iden()
    }

    // migrations() ...
}
```

## Writing Migration

Generate timestamped file, or manually use `mYYYYMMDD_HHMMSS_name.rs`; `--local-time` uses local time:

```shell
sea-orm-cli migrate generate create_post_table
sea-orm-cli migrate generate "create post table" --local-time
```

Every migration derives recorded name and implements both directions. `down` reverses dependencies: drop index or foreign key before its table.

```rust
use sea_orm_migration::{prelude::*, schema::*};

#[derive(DeriveMigrationName)]
pub struct Migration;

#[derive(Iden)]
enum Post { Table, Id, Title, Text }

#[async_trait]
impl MigrationTrait for Migration {
    async fn up(&self, manager: &SchemaManager) -> Result<(), DbErr> {
        manager.create_table(
            Table::create().table(Post::Table).if_not_exists()
                .col(pk_auto(Post::Id))
                .col(string(Post::Title))
                .col(string(Post::Text)),
        ).await?;
        manager.create_index(
            Index::create().if_not_exists().name("idx-post_title")
                .table(Post::Table).col(Post::Title),
        ).await?;
        Ok(())
    }

    async fn down(&self, manager: &SchemaManager) -> Result<(), DbErr> {
        manager.drop_index(Index::drop().name("idx-post_title")).await?;
        manager.drop_table(Table::drop().table(Post::Table)).await?;
        Ok(())
    }
}
```

Register every module in `migration/src/lib.rs`; `migrations()` lists chronological order:

```rust
pub use sea_orm_migration::*;

mod m20260813_120000_create_post_table;

pub struct Migrator;

#[async_trait]
impl MigratorTrait for Migrator {
    fn migrations() -> Vec<Box<dyn MigrationTrait>> {
        vec![Box::new(m20260813_120000_create_post_table::Migration)]
    }
}
```

`SchemaManager` also has `create_foreign_key`, `alter_table`, `rename_table`, `truncate_table`, `drop_foreign_key`, `has_table`, `has_column`, `has_index`; PostgreSQL also has `create_type`, `alter_type`, `drop_type`. For portable conditional columns, inspect first: MySQL lacks `ADD COLUMN IF NOT EXISTS`.

```rust
if !manager.has_column("post", "published_at").await? {
    manager.alter_table(
        Table::alter().table(Post::Table)
            .add_column(date_time_null("published_at")),
    ).await?;
}
```

For raw SQL use `manager.get_connection()`: `execute_unprepared` has no bindings; use `execute_raw(Statement::from_sql_and_values(...))` for bound values. Raw SQL loses SeaQuery multi-backend compatibility. PostgreSQL migrations are atomic; MySQL and SQLite are not. Explicit transaction needed when a group, such as seed data, must be atomic there.

## Running Migration

Set `DATABASE_URL`, then use either generated CLI:

```shell
# sea-orm-cli runs cargo run --manifest-path ./migration/Cargo.toml -- COMMAND
sea-orm-cli migrate up
sea-orm-cli migrate up -n 10
sea-orm-cli migrate down
sea-orm-cli migrate down -n 10
sea-orm-cli migrate status

cd migration
cargo run -- up
```

Commands: `init`, `generate`, `up`, `down`, `status`, `fresh`, `refresh`, `reset`. `fresh` drops all tables then applies every migration; `refresh` rolls back every applied migration then reapplies; `reset` rolls back every applied migration. Use destructive commands only against intended database.

Run programmatically after connecting:

```rust
use migration::{Migrator, MigratorTrait};
use sea_orm::Database;

let db = Database::connect(&database_url).await?;
Migrator::up(&db, None).await?;       // all pending
// Migrator::up(&db, Some(10)).await?; // at most 10 pending
// Migrator::down(&db, Some(1)).await?; // last applied migration
// Migrator::status(&db).await?;
```

For PostgreSQL schema other than `public`, pass `-s my_schema` to either CLI, or set connection search path:

```rust
use sea_orm::{ConnectOptions, Database};

let options = ConnectOptions::new("postgres://root:root@localhost/database")
    .set_schema_search_path("my_schema")
    .to_owned();
let db = Database::connect(options).await?;
Migrator::up(&db, None).await?;
```

Inspect records when app needs them:

```rust
let pending = Migrator::get_pending_migrations(&db).await?;
let applied = Migrator::get_applied_migrations(&db).await?;
```

## Seeding Data

Seed only versioned data required by schema. Migration record prevents completed `up` reruns, but interrupted-deployment retries need database unique key plus conflict-safe insert, never check-then-insert race.

For one non-critical seed, get `SchemaManager` connection; insert through SeaORM entity or SeaQuery:

```rust
use sea_orm_migration::sea_orm::{entity::*, query::*};

let db = manager.get_connection();
cake::ActiveModel {
    name: Set("Cheesecake".to_owned()),
    ..Default::default()
}.insert(db).await?;
```

For a seed set that must all exist or all be absent: make stable key unique, begin explicitly, commit only after all operations. Uncommitted transaction rolls back on error; critical on MySQL and SQLite, where DDL is not automatically atomic:

```rust
use sea_orm_migration::sea_orm::{
    entity::*, query::*, sea_query::OnConflict, TransactionTrait,
};

let db = manager.get_connection();
let txn = db.begin().await?;

role::Entity::insert_many([
    role::ActiveModel { code: Set("admin".to_owned()), ..Default::default() },
    role::ActiveModel { code: Set("member".to_owned()), ..Default::default() },
])
.on_conflict(OnConflict::column(role::Column::Code).do_nothing().to_owned())
.exec(&txn)
.await?;

txn.commit().await?;
```

Create unique key in same migration, for example unique `code` index after table. SeaORM builder's `ON CONFLICT DO NOTHING` is portable, including MySQL form: retries preserve stable-key rows, not duplicates.

`down` deletes only versioned seed rows by stable key before table drop. Write deletion explicitly: table drop removes rows incidentally but neither documents nor preserves selective rollback.

```rust
use sea_orm_migration::sea_orm::sea_query::{Expr, Query};

let seeds = Query::delete()
    .from_table(Role::Table)
    .and_where(Expr::col(Role::Code).is_in(["admin", "member"]))
    .to_owned();
manager.execute(&seeds).await?;
manager.drop_table(Table::drop().table(Role::Table)).await?;
```

Do not use `fresh`, `refresh`, or `reset` to compensate for seed failure: they affect unrelated applied migrations.

## Reference

- https://www.sea-ql.org/SeaORM/docs/migration/setting-up-migration/
- https://www.sea-ql.org/SeaORM/docs/migration/writing-migration/
- https://www.sea-ql.org/SeaORM/docs/migration/running-migration/
- https://www.sea-ql.org/SeaORM/docs/migration/seeding-data/
