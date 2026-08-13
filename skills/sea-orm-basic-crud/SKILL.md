---
name: sea-orm-basic-crud
description: Use when an agent needs to implement or review SeaORM 2.0 CRUD, JSON mapping, raw SQL, or custom ActiveModel DTOs.
---

# SeaORM 2.0 Basic CRUD

`Entity` describes a table and starts queries, `Model` is a retrieved row, and `ActiveModel` is a write payload whose fields track database emission. Examples use generated `cake` and `fruit` entities and `db: &DatabaseConnection`.

```toml
[dependencies]
sea-orm = { version = "2.0", features = ["macros", "runtime-tokio-rustls", "sqlx-postgres"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

## When to Use

- Read into `Model`; convert to `ActiveModel` before changes.
- Use `ActiveModel` for insert, targeted update, or `save`.
- Use builders for ordinary SQL; use `raw_sql!` only when builder cannot express it.

## Basic Schema

Documentation schema: `cake` one-to-many `fruit`, `cake` many-to-many `filling`, `cake_filling` junction table. Generated entity modules contain:

- `Entity`: implements `EntityTrait`; starts `find`, `insert`, `update_many`, delete builders.
- `Model`: fully selected row; `into_active_model()` edits it.
- `ActiveModel`: columns wrapped in `ActiveValue`; appropriate fields emit on insert/update.
- `Column`: typed identifiers for filters, ordering, bulk mutations.

## SELECT: find, filter, sort, paging

`find_by_id` accepts scalar or composite primary-key tuple. `one`: `Result<Option<Model>, DbErr>`; `all`: `Result<Vec<Model>, DbErr>`.

```rust
use sea_orm::{ColumnTrait, EntityTrait, QueryFilter, QueryOrder};

let cake = cake::Entity::find_by_id(1).one(db).await?;
let link = cake_filling::Entity::find_by_id((6, 8)).one(db).await?;

let cakes = cake::Entity::find()
    .filter(cake::Column::Name.contains("chocolate"))
    .order_by_asc(cake::Column::Name)
    .all(db)
    .await?;
```

For page-number iteration, order deterministically, `paginate`, then fetch batches. For keyset pagination, `cursor_by`; `after`/`before` bound ordered range, `first`/`last` select window.

```rust
use sea_orm::{CursorTrait, EntityTrait, PaginatorTrait, QueryOrder};

let mut pages = cake::Entity::find()
    .order_by_asc(cake::Column::Id)
    .paginate(db, 50);
while let Some(batch) = pages.fetch_and_next().await? {
    // batch: Vec<cake::Model>
}

let mut cursor = cake::Entity::find().cursor_by(cake::Column::Id);
cursor.after(1).before(100);
let first_ten = cursor.first(10).all(db).await?;
```

With `#[sea_orm::model]` or `#[sea_orm::compact_model]`, `COLUMN` provides field-type-aware conditions, e.g. `cake::COLUMN.name.contains("chocolate")`; older `Column` accepts compatible SeaQuery values. `#[sea_orm(unique)]` generates `find_by_<field>` and `filter_by_<field>`.

## ActiveModel & ActiveValue

Each `ActiveModel` field is:

- `Set(value)`: send `value`; `Set(None)` writes SQL `NULL` for nullable columns.
- `Unchanged(value)`: loaded database value; omit from `UPDATE` assignments. For one-row update, primary-key `ActiveValue` supplies target condition and is not updated.
- `NotSet`: omit column. Fresh default `ActiveModel` uses it; database default generates insert value and it excludes column from update.

Queried `Model` conversion produces `Unchanged`. `set_if_not_equals` retains `Unchanged` for equal values; `is_changed()` reports any `Set`; `try_into_model()` requires every value and returns `DbErr::AttrNotSet` for `NotSet`.

```rust
use sea_orm::{ActiveModelTrait, ActiveValue::{NotSet, Set, Unchanged}};

let new_fruit = fruit::ActiveModel {
    id: NotSet,                         // database-generated id
    name: Set("Orange".into()),
    cake_id: Set(None),                 // explicitly SQL NULL
};

let mut active: fruit::ActiveModel = fruit::Entity::find_by_id(1)
    .one(db).await?.expect("existing fruit").into();
active.name = Set("Blood orange".into());
assert!(active.is_changed());
```

## INSERT: insert one & insert many

`active.insert(db)` returns fresh `Model`, including database-generated values. `Entity::insert(active).exec(db)` returns `InsertResult`; `last_insert_id` has entity primary-key type.

```rust
use sea_orm::{ActiveModelTrait, ActiveValue::Set, EntityTrait};

let pear: fruit::Model = fruit::ActiveModel {
    name: Set("Pear".into()),
    ..Default::default()
}.insert(db).await?;

let result = fruit::Entity::insert(fruit::ActiveModel {
    name: Set("Apple".into()),
    ..Default::default()
}).exec(db).await?;
let id = result.last_insert_id;
```

`Entity::insert_many(items).exec(db)` returns `InsertManyResult`; in 2.0 `last_insert_id` is `Option<PrimaryKey>`. Empty iterator is valid and returns `None`. Postgres and SQLite `exec_with_returning` returns inserted `Model` for one row or `Vec<Model>` for many; use `exec_with_returning_keys` for only primary keys.

Use `on_conflict` with `sea_query::OnConflict` for upsert. `DO NOTHING` with no inserted row normally returns `DbErr::RecordNotInserted`; use `try_insert()` when `Conflicted` is expected.

## Return Shape: choose before mutating

Choose operation from needed result; do not add read after bulk mutation:

| Operation | Result |
| --- | --- |
| `active.insert(db)` / `active.update(db)` | fresh `Model` |
| `active.save(db)` | `ActiveModel`; insert or update from primary-key state, never upsert |
| `Entity::insert(active).exec(db)` | `InsertResult` with `last_insert_id` |
| `Entity::insert_many(items).exec(db)` | `InsertManyResult` with `Option<PrimaryKey>` `last_insert_id`; empty input is `None` |
| `update_many` / `delete_many` / non-returning `delete_by_id` `.exec(db)` | result with `rows_affected` |
| supported `.exec_with_returning(db)` | inserted/updated/deleted model(s); `delete_by_id` is `Option<Model>` |

## UPDATE: find & save, update many

Fetch `Model`, convert, set only changed fields, then `update`; it returns fresh `Model`. `reset(column)` marks unchanged field `Set`; `reset_all()` forces all fields dirty.

```rust
use sea_orm::{ActiveModelTrait, ActiveValue::Set, EntityTrait};

let mut pear: fruit::ActiveModel = fruit::Entity::find_by_id(28)
    .one(db).await?.expect("fruit exists").into();
pear.name = Set("Sweet pear".into());
let pear: fruit::Model = pear.update(db).await?;
```

For one SQL update across rows, do not fetch models. `update_many.exec` returns `UpdateResult` (`rows_affected`); use `col_expr` for expressions. `exec_with_returning` returns `Vec<Model>` on Postgres and SQLite (MariaDB needs `mariadb-use-returning`).

```rust
use sea_orm::{ColumnTrait, EntityTrait, QueryFilter};
use sea_orm::sea_query::Expr;

let updated = fruit::Entity::update_many()
    .col_expr(fruit::Column::CakeId, Expr::value(1))
    .filter(fruit::Column::Name.contains("Apple"))
    .exec(db)
    .await?;
assert!(updated.rows_affected >= 1);
```

## SAVE: Insert or Update

`ActiveModelTrait::save` uses primary-key state: `NotSet` inserts; `Set` or `Unchanged` updates. Returns `ActiveModel`, not `Model`. After insert generated primary key is `Unchanged`, so later changed `save` updates same row. `save` is not SQL upsert.

```rust
use sea_orm::{ActiveModelTrait, ActiveValue::{NotSet, Set}};

let mut banana = fruit::ActiveModel {
    id: NotSet,
    name: Set("Banana".into()),
    ..Default::default()
}.save(db).await?; // INSERT

banana.name = Set("Banana Mongo".into());
let banana = banana.save(db).await?; // UPDATE
```

## DELETE: delete one & delete many

Delete loaded row with `ModelTrait::delete`, or skip read with `Entity::delete_by_id(id).exec(db)`. Both return `DeleteResult`; inspect `rows_affected`. In 2.0 `delete_by_id` is validated single-row builder; `exec_with_returning` returns `Option<Model>`.

```rust
use sea_orm::{ColumnTrait, EntityTrait, ModelTrait, QueryFilter};

let deleted = fruit::Entity::delete_by_id(38).exec(db).await?;
assert_eq!(deleted.rows_affected, 1);

let removed = fruit::Entity::delete_many()
    .filter(fruit::Column::Name.contains("Orange"))
    .exec(db)
    .await?;
```

`delete_many().exec_with_returning(db)` returns `Vec<Model>` where supported: Postgres and SQLite, or MariaDB with `mariadb-use-returning`. `#[sea_orm(unique)]` generates `delete_by_<field>`.

## JSON

Add `into_json()` before `one`, `all`, or `paginate` to retrieve `serde_json::Value` rather than `Model`.

```rust
use sea_orm::EntityTrait;
let cake: Option<serde_json::Value> = cake::Entity::find_by_id(1)
    .into_json()
    .one(db)
    .await?;
```

For JSON write input, derive `Serialize` and `Deserialize` on entity `Model`. In 2.0 omitted JSON fields are `NotSet`. `set_from_json` updates only non-primary-key fields; `from_json` builds new active model.

```rust
use sea_orm::{ActiveModelTrait, ActiveValue::Set};
use serde_json::json;

let mut active_fruit = fruit::ActiveModel { id: Set(1), ..Default::default() };
active_fruit.set_from_json(json!({ "id": 8, "name": "Apple", "cake_id": 1 }))?;
// id remains Set(1); name and cake_id are Set from JSON.

let new_fruit = fruit::ActiveModel::from_json(json!({ "name": "Apple" }))?;
// omitted id and cake_id are NotSet
```

## Raw SQL Query

Prefer typed builder; use `raw_sql!` when it cannot model query. Macro binds `{value}` and expands `({..ids})` to backend-aware placeholders; never interpolate untrusted values into SQL text.

```rust
use sea_orm::{DbBackend::Postgres, EntityTrait, FromQueryResult};
use sea_orm::sea_query::raw_sql;

let id = 1;
let ids = [2, 3, 4];
let cake = cake::Entity::find()
    .from_raw_sql(raw_sql!(Postgres,
        r#"SELECT "cake"."id", "cake"."name" FROM "cake" WHERE "id" = {id}"#))
    .one(db)
    .await?;

#[derive(FromQueryResult)]
struct CakeName { name: String }
let names = CakeName::find_by_statement(raw_sql!(Postgres,
    r#"SELECT "name" FROM "cake" WHERE "id" IN ({..ids})"#))
    .all(db)
    .await?;
```

Map raw rows to entity `Model` with `Entity::find().from_raw_sql`, custom `#[derive(FromQueryResult)]` with `find_by_statement`, or use `query_one_raw`/`query_all_raw` for `QueryResult` and `try_get`. Use `execute_raw(Statement::from_string(...))` for non-query SQL and inspect `ExecResult::rows_affected()`. `execute_unprepared` is only for trusted, parameterless administrative SQL.

## Custom Active Model

For request DTO with fewer or differently typed fields, derive `DeriveIntoActiveModel`. Ordinary fields become `Set`; omitted entity fields remain `NotSet`, preventing accidental updates. PATCH values need omit/set `NULL`/set value: `Option<Option<T>>`; `None` omits, `Some(None)` writes SQL `NULL`, `Some(Some(v))` writes `v`.

```rust
use sea_orm::{DeriveIntoActiveModel, IntoActiveModel};

#[derive(DeriveIntoActiveModel)]
#[sea_orm(active_model = "fruit::ActiveModel")]
struct UpdateFruit {
    cake_id: Option<Option<i32>>,
}

let patch = UpdateFruit { cake_id: Some(None) }.into_active_model();
// patch.cake_id is Set(None); omitted id and name are NotSet.
```

Use `#[sea_orm(set(field = "expr"))]` for computed absent fields, `#[sea_orm(default = "expr")]` for `Option<T>` fallback, `#[sea_orm(ignore)]` for DTO-only fields, and `exhaustive` to require every active-model field. `DerivePartialModel` with `into_active_model` reuses partial select struct for writes.

## Reference

- https://www.sea-ql.org/SeaORM/docs/basic-crud/basic-schema/
- https://www.sea-ql.org/SeaORM/docs/basic-crud/select/
- https://www.sea-ql.org/SeaORM/docs/basic-crud/active-model/
- https://www.sea-ql.org/SeaORM/docs/basic-crud/insert/
- https://www.sea-ql.org/SeaORM/docs/basic-crud/update/
- https://www.sea-ql.org/SeaORM/docs/basic-crud/save/
- https://www.sea-ql.org/SeaORM/docs/basic-crud/delete/
- https://www.sea-ql.org/SeaORM/docs/basic-crud/json/
- https://www.sea-ql.org/SeaORM/docs/basic-crud/raw-sql/
- https://www.sea-ql.org/SeaORM/docs/basic-crud/custom-active-model/
