---
name: sea-orm-advanced-queries
description: Use when building SeaORM 2.0 custom projections, expressions, conditional or aggregate queries, custom join conditions, bespoke aliased report joins, subqueries, transactions, streams, nested ActiveModels, or DbErr/SqlErr handling.
---

# SeaORM 2.0 Advanced Queries

Build from entity columns and SeaQuery expressions, not interpolated SQL. Make result shape, aliases, grouping, transaction lifetime explicit. Map incomplete entity projections to dedicated types.

## When to Use

- Computed columns, partial rows, aggregates, aliases, custom joins.
- Runtime filters, `EXISTS`, subqueries, transactions needing explicit behavior.
- Incremental large-result processing or atomic relation-graph saves.

## Custom Select

`find()` selects every column. For partial projections, start `select_only()`, then `column`, `columns`, `column_as`, or `expr_as`.

```rust
use sea_orm::{FromQueryResult, QuerySelect};
use sea_query::{Expr, Func};

#[derive(FromQueryResult)]
struct CakeSummary {
    id: i32,
    name_upper: String,
}

let rows = cake::Entity::find()
    .select_only()
    .column(cake::Column::Id)
    .expr_as(Func::upper(Expr::col(cake::Column::Name)), "name_upper")
    .into_model::<CakeSummary>()
    .all(db)
    .await?;
```

For ad-hoc scalar/tuple results, select intended tuple order and use `into_tuple()`:

```rust
let names_and_counts: Vec<(String, i64)> = cake::Entity::find()
    .select_only()
    .column(cake::Column::Name)
    .column(cake::Column::Id.count())
    .group_by(cake::Column::Name)
    .into_tuple()
    .all(db)
    .await?;
```

For reusable projections directly mapping to an entity, use `#[derive(DerivePartialModel)]` and `#[sea_orm(entity = "cake::Entity")]`. `#[sea_orm(from_col = "id")]` remaps source column; `#[sea_orm(from_expr = "...")]` supplies SeaQuery expression. A missing, unskipped projected field is tolerated only for `Option<T>`, becoming `None`. Use `#[sea_orm(skip)]` for separately populated, non-deserialized fields.

## Conditional Expressions

Pass `Condition` or `SimpleExpr` to `filter`; `Condition::all()` is `AND`, `Condition::any()` is `OR`. Nest with `add`, not manual parentheses.

```rust
use sea_orm::{Condition, EntityTrait, QueryFilter};

let cakes = cake::Entity::find()
    .filter(
        Condition::any()
            .add(
                Condition::all()
                    .add(cake::Column::Id.lte(30))
                    .add(cake::Column::Name.contains("Chocolate")),
            )
            .add(cake::Column::Name.contains("Cheese")),
    )
    .all(db)
    .await?;
```

`has_related(related_entity, condition)` creates relation-aware `EXISTS` and resolves declared 1-1, 1-N, M-N paths. `apply_if(option, |query, value| ...)` skips absent request parameters while retaining fluent queries. Use `filter` for rows; `having` for aggregates.

## Aggregate Functions

`ColumnTrait`: `count`, `sum`, `min`, `max`, `avg`. Alias aggregates; group every selected non-aggregate expression as target database requires; use `having` after `group_by`.

```rust
use sea_orm::{FromQueryResult, QuerySelect};
use rust_decimal::Decimal;
use sea_query::ExprTrait;

#[derive(FromQueryResult)]
struct CustomerTotal {
    id: i32,
    name: String,
    total_spent: Option<Decimal>,
    order_count: i64,
}

let totals = customer::Entity::find()
    .left_join(order::Entity)
    .select_only()
    .column(customer::Column::Id)
    .column(customer::Column::Name)
    .column_as(order::Column::Total.sum(), "total_spent")
    .column_as(order::Column::Id.count(), "order_count")
    .group_by(customer::Column::Id)
    .group_by(customer::Column::Name)
    .having(order::Column::Total.sum().gt(100))
    .into_model::<CustomerTotal>()
    .all(db)
    .await?;
```

Unmatched `LEFT JOIN` groups make `SUM`, `MIN`, `MAX`, `AVG` `NULL`; map to `Option<T>` or use database-appropriate `COALESCE` for a concrete default. Count nullable right key (`order::Column::Id`) for `0`; `COUNT(*)` counts null-extended join row.

A backend permitting select aliases in `HAVING` accepts `Expr::col("alias")`; prefer aggregate expression itself for portable SQL.

## Custom Join Condition

For stable domain-level derived-relation constraints, use `#[sea_orm(on_condition = r#"..."#)]`; expression must implement `IntoCondition`.

```rust
#[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
pub enum Relation {
    #[sea_orm(
        has_many = "super::fruit::Entity",
        on_condition = r#"super::fruit::Column::Name.like("%tropical%")"#
    )]
    TropicalFruit,
}
```

For one-off joins, customize `RelationDef` with `on_condition(|left, right| ...)`; qualify columns through closure aliases, especially repeated tables.

```rust
use sea_orm::{JoinType, RelationTrait};
use sea_query::Expr;

let query = cake::Entity::find().join(
    JoinType::LeftJoin,
    cake::Relation::Fruit.def().on_condition(|_left, right| {
        Expr::col((right, fruit::Column::Name))
            .like("%tropical%")
            .into_condition()
    }),
);
```

Join conditions combine with `AND`. Use `condition_type(ConditionType::Any)` or relation `condition_type = "any"` only when relation predicate must join with `OR`. Use `join_as`, then `from_alias` for next relation hop; otherwise generated `ON` may reference unaliased table.

## Sub Query

Build SeaQuery subquery, call `to_owned()`, pass to `in_subquery`/`not_in_subquery`.

```rust
use sea_orm::QueryFilter;
use sea_query::Query;

let largest_id = Query::select()
    .expr(cake::Column::Id.max())
    .from(cake::Entity)
    .to_owned();

let cake = cake::Entity::find()
    .filter(cake::Column::Id.in_subquery(largest_id))
    .one(db)
    .await?;
```

Use for `IN`/`NOT IN`. Prefer `has_related` when only testing declared relation existence: it expresses intent and builds correlation.

## Transaction

Use `TransactionTrait::transaction` for normal atomic units: `Ok` commits, `Err` rolls back. Pin async closure with `Box::pin`.

```rust
use sea_orm::{DbErr, Set, TransactionTrait};

db.transaction::<_, (), DbErr>(|txn| {
    Box::pin(async move {
        bakery::ActiveModel {
            name: Set("SeaSide Bakery".into()),
            ..Default::default()
        }
        .save(txn)
        .await?;
        Ok(())
    })
})
.await?;
```

Use `begin().await?` when closure cannot meet lifetime constraints. Execute through `&txn`, explicitly `commit`/`rollback`; dropping uncommitted transaction rolls back. Nested transactions use database `SAVEPOINT`s. `transaction_with_config`/`begin_with_config` accept `IsolationLevel` and `AccessMode`, implemented only for MySQL/Postgres; default `AccessMode::ReadWrite`.

Keep `Result<_, DbErr>` from `.transaction(...).await`; classify afterward. Constraint errors must leave closure as `Err`, so rollback precedes `error.sql_err()` mapping to application conflict. Handling inside closure then returning `Ok` commits earlier writes.

## Streaming

Call `stream(db).await?` on `Select`; consume `TryStreamExt::try_next` to avoid collecting whole result set.

```rust
use futures::TryStreamExt;

let mut stream = fruit::Entity::find()
    .filter(fruit::Column::Name.contains("a"))
    .order_by_asc(fruit::Column::Name)
    .stream(db)
    .await?;

while let Some(model) = stream.try_next().await? {
    let active: fruit::ActiveModel = model.into();
    // Process one row; do not retain the stream longer than necessary.
}
```

A stream exclusively holds its connection until dropped. Scope/drop streams promptly; size pool for concurrent streams. Do not use same borrowed connection while stream lives. If reads/writes share transaction: stream bounded page to local batch, end stream scope, then write batch through transaction; do not retain unbounded feed.

## Nested Active Model

SeaORM 2.0 nested ActiveModels atomically save relation trees, order inserts/updates for foreign keys, and detect changes through `Set`, `Unchanged`, `NotSet`.

```rust
let user = user::ActiveModel::builder()
    .set_name("Bob")
    .set_email("bob@sea-ql.org")
    .set_profile(profile::ActiveModel::builder().set_picture("image.jpg"))
    .add_post(
        post::ActiveModel::builder()
            .set_title("Nice weather")
            .add_tag(tag::ActiveModel::builder().set_tag("sunny")),
    )
    .save(db)
    .await?;
```

`HasMany` defaults to non-destructive append. Use `replace_all` only when supplied children are complete desired set: 1-N deletes omitted children; M-N removes only omitted junction-table associations, not related rows. Prefer `save` over manual `insert`/`update`; unchanged tree saves no-op. `cascade_delete` walks client-side dependencies when database cascade unavailable. Features require `#[sea_orm::model]`, unavailable to `#[sea_orm::compact_model]`.

## Error Handling

Runtime failures are `DbErr`. Classify common SQL constraints with `DbErr::sql_err()` and `SqlErr`, not backend-specific message parsing.

```rust
use sea_orm::{DbErr, SqlErr};

match cake.into_active_model().insert(db).await {
    Err(error) if matches!(error.sql_err(), Some(SqlErr::UniqueConstraintViolation(_))) => {
        // Return a conflict response.
    }
    Err(error) => return Err(error),
    Ok(model) => { /* use model */ }
}
```

SeaORM 2.0 returns `DbErr::PrimaryKeyNotSet` for invalid `Update::one`/`Delete::one`; call `.validate()?` before `.build()` to surface construction error. It returns `DbErr::BackendNotSupported` for `exec_with_returning_keys` on MySQL, `DbErr::AccessDenied` when `RestrictedConnection` blocks RBAC. Match `DbErr::Exec(RuntimeErr::SqlxError(sqlx::Error::Database(error)))` only when application genuinely needs backend-specific code.

## Advanced Joins

Prefer SeaORM 2.0 nested selects/entity loaders for ordinary multi-relation reads. For bespoke reports use focused `FromQueryResult`/partial model, identifier types not string table names, explicit aliases, `join_as` then `from_alias` for each path.

```rust
#[derive(DeriveIden, Clone, Copy)]
struct Base;

let products = complex_product::Entity::find()
    .select_only()
    .tbl_col_as((Base, base_product::Column::Id), "id")
    .tbl_col_as((Base, base_product::Column::Name), "name")
    .column_as(product_type::Column::Name, "type")
    .join_as(
        JoinType::InnerJoin,
        complex_product::Relation::BaseProduct.def(),
        Base,
    )
    .join(
        JoinType::InnerJoin,
        base_product::Relation::ProductType.def().from_alias(Base),
    )
    .into_model::<ComplexProduct>()
    .all(db)
    .await?;
```

For diamond topology, alias each branch and `from_alias` before joining its next relation. Build optional report filters with `Condition::add_option`, preserving one query definition without placeholder predicates. For bespoke parent projection needing collection, fetch children once with `is_in(parent_ids)` and associate by parent ID, not by duplicating parent rows in wide join.

## Reference

- https://www.sea-ql.org/SeaORM/docs/advanced-query/custom-select/
- https://www.sea-ql.org/SeaORM/docs/advanced-query/conditional-expression/
- https://www.sea-ql.org/SeaORM/docs/advanced-query/aggregate-function/
- https://www.sea-ql.org/SeaORM/docs/advanced-query/custom-join-condition/
- https://www.sea-ql.org/SeaORM/docs/advanced-query/subquery/
- https://www.sea-ql.org/SeaORM/docs/advanced-query/transaction/
- https://www.sea-ql.org/SeaORM/docs/advanced-query/streaming/
- https://www.sea-ql.org/SeaORM/docs/advanced-query/nested-active-model/
- https://www.sea-ql.org/SeaORM/docs/advanced-query/error-handling/
- https://www.sea-ql.org/SeaORM/docs/advanced-query/advanced-joins/
