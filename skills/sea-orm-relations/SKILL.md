---
name: sea-orm-relations
description: Use when an agent defines SeaORM 2.0 entity cardinality, loads or joins relations, shapes relational results, or filters an entity by a related entity with `has_related`.
---

# SeaORM 2.0 Relations

Relations are directed `RelationDef` arrows. Put foreign key and `belongs_to` on referencing entity; inverse `has_one` or `has_many` on referenced entity. Use direct relation for one unambiguous path; `Linked` for multi-hop or ambiguous paths.

Examples use official bakery entities: `cake`, `fruit`, `filling`, `cake_filling` junction table.

## When to Use

- Define foreign-key cardinality in `#[sea_orm::model]` or `#[sea_orm::compact_model]` entities.
- Traverse with joins, `find_*_related`, `Linked`, or loaders.
- Avoid duplicated joined rows or N+1 loading a relation graph.
- Project joined rows into nested partial models or consolidate multi-selects.
- Filter an entity by a related-entity condition.

## One to One

`HasOne<T>` on owner; `BelongsTo<T>` on foreign-key entity. Enforce one-to-one with a unique foreign key: `has_one` alone creates no uniqueness constraint.

```rust
// cake.rs
#[sea_orm::model]
#[derive(DeriveEntityModel)]
#[sea_orm(table_name = "cake")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    #[sea_orm(has_one)]
    pub fruit: HasOne<super::fruit::Entity>,
}

// fruit.rs
#[sea_orm::model]
#[derive(DeriveEntityModel)]
#[sea_orm(table_name = "fruit")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    #[sea_orm(unique)]
    pub cake_id: Option<i32>,
    #[sea_orm(belongs_to, from = "cake_id", to = "id")]
    pub cake: BelongsTo<Option<super::cake::Entity>>,
}
```

Macro expands fields into `Relation` variants and `Related` implementations. Match `BelongsTo` optionality to nullable foreign key.

## One to Many

`HasMany<T>` on one side; `BelongsTo<T>` on many side. Many-side foreign key is not unique.

```rust
// cake.rs
#[sea_orm(has_many)]
pub fruits: HasMany<super::fruit::Entity>,

// fruit.rs
pub cake_id: Option<i32>,
#[sea_orm(belongs_to, from = "cake_id", to = "id")]
pub cake: BelongsTo<Option<super::cake::Entity>>,
```

Composite foreign keys use tuple column names on both sides; target columns must form a unique key.

```rust
#[sea_orm(belongs_to,
    from = "(left_id, right_id)",
    to = "(left_id, right_id)")]
pub parent: BelongsTo<super::parent::Entity>,
```

## Many to Many

Model M-N with junction entity holding two `belongs_to` relations. Endpoints declare `has_many` through junction with `via`.

```rust
// cake.rs
#[sea_orm(has_many, via = "cake_filling")]
pub fillings: HasMany<super::filling::Entity>,

// cake_filling.rs
#[sea_orm(primary_key, auto_increment = false)]
pub cake_id: i32,
#[sea_orm(primary_key, auto_increment = false)]
pub filling_id: i32,
#[sea_orm(belongs_to, from = "cake_id", to = "id")]
pub cake: BelongsTo<super::cake::Entity>,
#[sea_orm(belongs_to, from = "filling_id", to = "id")]
pub filling: BelongsTo<super::filling::Entity>,
```

Traversal is `cake -> cake_filling -> filling`: `via` reverses `CakeFilling -> Cake`, then uses `CakeFilling -> Filling`. Generated `Related` is unavailable if multiple relations connect same entities; join a specific `Relation` or define `Linked`.

## Complex Relations

Implement `Linked` for reusable multi-hop paths or multiple possible join paths. `link` orders `FromEntity` to `ToEntity`; `.rev()` stored arrows pointing backward.

```rust
pub struct CakeToFilling;

impl Linked for CakeToFilling {
    type FromEntity = cake::Entity;
    type ToEntity = filling::Entity;

    fn link(&self) -> Vec<RelationDef> {
        vec![
            cake_filling::Relation::Cake.def().rev(),
            cake_filling::Relation::Filling.def(),
        ]
    }
}

let fillings = cake_model.find_linked(CakeToFilling).all(db).await?;
let cakes_and_fillings = cake::Entity::find()
    .find_also_linked(CakeToFilling)
    .all(db)
    .await?;
```

`find_also_linked` matches `find_also_related`; `find_with_linked` matches `find_with_related`.

Self references: use `self_ref` and distinct relation names. Diamonds (for example, bakery manager and cashier both workers): give each `belongs_to` a distinct `relation_enum`; inverse `has_many` selects branch with `via_rel`.

```rust
#[sea_orm(has_many, relation_enum = "BakeryManager", via_rel = "Manager")]
pub manager_of: HasMany<super::bakery::Entity>,
#[sea_orm(has_many, relation_enum = "BakeryCashier", via_rel = "Cashier")]
pub cashier_of: HasMany<super::bakery::Entity>,
```

## Choose the Result Shape Before the API

| Need | Prefer | Reason |
| --- | --- | --- |
| Declared graph rooted at entity | Entity Loader, `.load().with(...)` | One-to-many and M-N batch IDs, not one query per parent. |
| Related records for fetched models | Model Loader, `load_one`/`load_many` | Batch load; preserve model order. |
| Predicate deciding root rows | `has_related` | Existence test; no related-row selection or duplication. |
| Related columns/value for retained root | Loader or join | Existence filter returns no related model or columns. |
| Tuple report from modest join | Multi-select, then `consolidate()` | Keep row shape until stable ordering groups it. |
| Custom nested projection/same entity twice | `DerivePartialModel` with `join_as` aliases | Aliases identify SQL sources and nested fields. |

`has_related` asks whether root is kept, not to load/join model. Filter wholesale orders with it; if UI needs each customer's tier badge, load or join `Customer`.

Joining entity twice requires distinct relation/table aliases. Nested field `alias` must match `join_as`, not Rust field name:

```rust
#[derive(DerivePartialModel)]
#[sea_orm(entity = "bakery::Entity")]
struct BakeryPeople {
    name: String,
    #[sea_orm(nested, alias = "manager")]
    manager: Option<WorkerName>,
    #[sea_orm(nested, alias = "cashier")]
    cashier: Option<WorkerName>,
}

#[derive(DerivePartialModel)]
#[sea_orm(entity = "worker::Entity")]
struct WorkerName {
    name: String,
}

let bakeries = bakery::Entity::find()
    .join_as(JoinType::LeftJoin, bakery::Relation::Manager.def(), "manager")
    .join_as(JoinType::LeftJoin, bakery::Relation::Cashier.def(), "cashier")
    .into_partial_model::<BakeryPeople>()
    .all(db)
    .await?;
```

## Model Loader

`LoaderTrait` batch-loads relations for fetched `Vec<Model>`: fetch parents once, all children with `IN (...)`; preserves input-model order and avoids repeated parent columns in large one-to-many joins.

```rust
let cakes: Vec<cake::Model> = cake::Entity::find().all(db).await?;
let fruits: Vec<Vec<fruit::Model>> = cakes.load_many(fruit::Entity, db).await?;

for (cake, fruits) in cakes.into_iter().zip(fruits) {
    // one cake and all of its fruits
}
```

Filter related select when needed:

```rust
let in_stock = cakes.load_many(
    fruit::Entity::find().filter(fruit::Column::Stock.gt(0)),
    db,
).await?;
```

Use separate `load_many` calls for independent relations from same parents. Prefer this to wide joins when collection side is large or M-N duplicates endpoint rows.

## Entity Loader

SeaORM 2.0 generates Entity Loader for `#[sea_orm::model]` and `#[sea_orm::compact_model]`. `Entity::load().with(...)` loads declared graphs into generated extended models without N+1.

```rust
let cake = cake::Entity::load()
    .filter_by_id(42)
    .with(fruit::Entity)
    .with((filling::Entity, ingredient::Entity))
    .one(db)
    .await?
    .unwrap();
```

One-to-one joins/selects up to three tables in one query. One-to-many/M-N use batched data-loader queries (M-N joins junction). Nested paths consolidate preceding IDs, so each level uses one query, not one per parent. Pagination:

```rust
let mut pages = user::Entity::load()
    .with(profile::Entity)
    .order_by_asc(user::Column::Id)
    .paginate(db, 10);

while let Some(users) = pages.fetch_and_next().await? {
    // `users` contains loaded extended user models
}
```

## Bakery Schema

Official bakery-chain test schema references a complex typed relation model used by subsequent relation documentation examples. Use it as shared context for richer relational models.

## Nested Selects

Nested projections turn joined SQL rows into nested Rust results. With `FromQueryResult`, clear default select list, alias overlapping columns, map aliases with `#[sea_orm(alias = "...")]` on nested type.

```rust
#[derive(FromQueryResult)]
struct CakeRow {
    id: i32,
    name: String,
    #[sea_orm(nested)]
    bakery: Option<BakeryRow>,
}

#[derive(FromQueryResult)]
struct BakeryRow {
    #[sea_orm(alias = "bakery_id")]
    id: i32,
    #[sea_orm(alias = "bakery_name")]
    name: String,
}

let cake = cake::Entity::find()
    .select_only()
    .column(cake::Column::Id)
    .column(cake::Column::Name)
    .column_as(bakery::Column::Id, "bakery_id")
    .column_as(bakery::Column::Name, "bakery_name")
    .left_join(bakery::Entity)
    .into_model::<CakeRow>()
    .one(db)
    .await?;
```

Since 2.0.0, prefer `DerivePartialModel` if generated aliases fit query. `#[sea_orm(nested)]` prefixes child columns with field name; `from_col` maps field to different entity column.

```rust
#[derive(DerivePartialModel)]
#[sea_orm(entity = "cake::Entity")]
struct CakeView {
    id: i32,
    name: String,
    #[sea_orm(nested)]
    bakery: Option<BakeryView>,
}

#[derive(DerivePartialModel)]
#[sea_orm(entity = "bakery::Entity")]
struct BakeryView {
    id: i32,
    #[sea_orm(from_col = "name")]
    brand: String,
}

let cake = cake::Entity::find()
    .left_join(bakery::Entity)
    .into_partial_model::<CakeView>()
    .one(db)
    .await?;
```

Nested field may be regular entity `Model`. With `left_join_linked` or `join_as`, set `#[sea_orm(nested, alias = "...")]` to actual table alias. For three-way path whose later entity is unrelated to root, use `join(JoinType::LeftJoin, relation.def())`, not `left_join`.

## Multi Selects

Use multi-selects when tuple-shaped joined models beat custom partial model. `find_also_related` joins first entity's relation; `and_also_related` continues from second.

```rust
let rows: Vec<(order::Model, Option<lineitem::Model>, Option<cake::Model>)> =
    order::Entity::find()
        .find_also_related(lineitem::Entity)
        .and_also_related(cake::Entity)
        .all(db)
        .await?;
```

Result is flat. Call `.consolidate()` after stable parent/child ordering to group repeated rows; shape follows join topology:

```rust
// Chain: Order -> LineItem -> Cake
let grouped: Vec<(order::Model, Vec<(lineitem::Model, Vec<cake::Model>)>)> =
    order::Entity::find()
        .find_also_related(lineitem::Entity)
        .and_also_related(cake::Entity)
        .order_by_asc(order::Column::Id)
        .order_by_asc(lineitem::Column::Id)
        .consolidate()
        .all(db)
        .await?;

// Star: Order -> Customer and Order -> LineItem
// Vec<(order::Model, Vec<customer::Model>, Vec<lineitem::Model>)>
```

Larger graphs: `find_also(from, to)` names each edge and selects up to six models. Use when topology cannot be first relation plus `and_also_related` calls.

## Relational Query

Filter by related entity with `has_related`: correlated `WHERE EXISTS`, direct and M-N relations.

```rust
let cakes = cake::Entity::find()
    .has_related(
        bakery::Entity,
        bakery::Column::Name.eq("SeaSide Bakery"),
    )
    .order_by_asc(cake::Column::Name)
    .all(db)
    .await?;

let alice_cakes = cake::Entity::find()
    .has_related(baker::Entity, baker::Column::Name.eq("Alice"))
    .all(db)
    .await?;
```

Use `has_related` only for root existence filtering: it returns no related columns. If UI needs related data, such as `Customer` tier for a badge, load or join `Customer`.

## Reference

- https://www.sea-ql.org/SeaORM/docs/relation/one-to-one/
- https://www.sea-ql.org/SeaORM/docs/relation/one-to-many/
- https://www.sea-ql.org/SeaORM/docs/relation/many-to-many/
- https://www.sea-ql.org/SeaORM/docs/relation/complex-relations/
- https://www.sea-ql.org/SeaORM/docs/relation/model-loader/
- https://www.sea-ql.org/SeaORM/docs/relation/entity-loader/
- https://www.sea-ql.org/SeaORM/docs/relation/bakery-schema/
- https://www.sea-ql.org/SeaORM/docs/relation/nested-selects/
- https://www.sea-ql.org/SeaORM/docs/relation/multi-selects/
- https://www.sea-ql.org/SeaORM/docs/relation/relational-query/
