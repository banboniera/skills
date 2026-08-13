---
name: sea-orm-writing-tests
description: Use when an agent needs SeaORM unit, mock, SQLite, or target-backend integration tests.
---

# SeaORM Testing

Choose cheapest test that falsifies contract:

| Contract | Test |
| --- | --- |
| Entity calculation or conversion | Pure Rust unit test |
| Repository/service branching or query composition | `MockDatabase` |
| CRUD through entity-backed, portable schema | Fresh SQLite-memory integration test |
| Production dialect, driver error, type, constraint, migration, or transaction behavior | Fresh live target-backend integration test |

`MockDatabase` returns arranged values; SQLite executes SQLite; neither proves a PostgreSQL- or MySQL-specific guarantee.

## When to Use

Use for SeaORM code needing confidence in domain logic, query orchestration, CRUD, or schema-backed integration behavior.

## Robust & Correct Tests

Test observable contract, not SeaORM plumbing:

- Keep entity/model calculations and transformations independently testable. SeaORM entities are ordinary Rust types; pure logic tests need neither `tokio` nor `sqlx`.
- Assert caller-visible values, ordering, errors, and mutation effects.
- Test repository/service query choice or composition with a mock; test persistence, constraints, and backend semantics live.
- Fresh state per integration test. Fast SQLite is broad coverage, not evidence production-only SQL or features work.

```rust
#[test]
fn triangle_area_is_two() {
    let triangle = Triangle {
        id: 1,
        p1: Point { x: 0.0, y: 0.0 },
        p2: Point { x: 2.0, y: 0.0 },
        p3: Point { x: 0.0, y: 2.0 },
    };

    assert!((triangle.area() - 2.0).abs() < 1e-8);
}
```

Do not add database setup when behavior is only Rust logic: failures become slower and less local.

## Mock Interface

Enable SeaORM `mock` feature; select backend rendering SQL:

```toml
[dev-dependencies]
sea-orm = { version = "2.0", features = ["mock"] }
```

`MockDatabase` starts empty. Queue results for each operation in execution order:

- `append_query_results` supplies result sets for `SELECT`-style operations.
- `append_exec_results` supplies `MockExecResult` for insert, update, delete execution.
- `into_connection()` produces a connection accepted by normal SeaORM CRUD API.

```rust
use sea_orm::{DatabaseBackend, DbErr, MockDatabase};

#[tokio::test]
async fn finds_the_expected_cake() -> Result<(), DbErr> {
    let db = MockDatabase::new(DatabaseBackend::Postgres)
        .append_query_results([vec![cake::Model {
            id: 1,
            name: "New York Cheese".to_owned(),
        }]])
        .into_connection();

    let cake = cake::Entity::find_by_id(1).one(&db).await?;
    assert_eq!(cake.map(|cake| cake.name), Some("New York Cheese".to_owned()));
    Ok(())
}
```

For writes, queue an execution result. `ActiveModel::insert` may also need a queued query result because SeaORM fetches inserted model.

```rust
use sea_orm::{DatabaseBackend, MockDatabase, MockExecResult};

let db = MockDatabase::new(DatabaseBackend::Postgres)
    .append_exec_results([MockExecResult {
        last_insert_id: 42,
        rows_affected: 1,
    }])
    .into_connection();
```

After operation, inspect generated transactions only when SQL shape and bound values are contract. Consume mock with `db.into_transaction_log()`; compare entries with `Transaction::from_sql_and_values(...)`, using same `DatabaseBackend` selected for mock.

### Mock limitations

Mock executes no SQL and models no stored rows, constraints, joins, migrations, transactions, or backend behavior. It returns queued values; a transaction-log assertion checks generated SQL, not database semantics.

### When `MockDatabase` is the wrong double

Do not use queued mock error as proof real database produces error. PostgreSQL `CITEXT` unique constraint, SQLSTATE/constraint-name mapping, or deadlock/retry behavior depends on server and driver. Mock may cover service branch **if** repository boundary supplies known duplicate outcome; cannot prove SeaORM receives and classifies real backend error. Test real schema/migration and application path against isolated target backend.

## Using SQLite

Use `sqlite::memory:` for high-level database-agnostic integration. Connect, create schema, then pass same `DbConn` to application operation:

```rust
use sea_orm::{
    ActiveModelTrait, ActiveValue::NotSet, ActiveValue::Set, ConnectOptions, Database, DbErr,
    EntityTrait,
};

#[tokio::test]
async fn creates_and_reads_a_post() -> Result<(), DbErr> {
    let mut options = ConnectOptions::new("sqlite::memory:");
    options.max_connections(1);
    let db = Database::connect(options).await?;

    db.get_schema_builder().register(post::Entity).apply(&db).await?;

    let created = post::ActiveModel {
        id: NotSet,
        title: Set("Title A".to_owned()),
        text: Set("Text A".to_owned()),
    }
    .insert(&db)
    .await?;

    let read = post::Entity::find_by_id(created.id)
        .one(&db)
        .await?
        .expect("the inserted post must be readable");
    assert_eq!(read.title, "Title A");
    Ok(())
}
```

`SchemaBuilder::register(...).apply(...)` derives table-creation order and foreign-key dependencies from registered entities. Prefer it for entity-represented schema; use manual DDL only when test needs schema outside that model. Keep schema setup and CRUD on same `DbConn`: SQLite memory database belongs to its connection. Set one connection if options could otherwise create pool.

SQLite is fast and avoids Docker database, useful for broad integration coverage. Still SQLite: do not substitute passing result for target-backend integration when code depends on database-specific SQL, driver errors, types, constraints, collations, transactions, or migrations. Give every live integration test isolated state (for example, per-test schema or reset database) and run production migrations needed for behavior.

## Reference

- https://www.sea-ql.org/SeaORM/docs/write-test/testing/
- https://www.sea-ql.org/SeaORM/docs/write-test/mock/
- https://www.sea-ql.org/SeaORM/docs/write-test/sqlite/
