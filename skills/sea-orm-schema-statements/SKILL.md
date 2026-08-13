---
name: sea-orm-schema-statements
description: Use when directly generating entity-derived SeaORM 2.0 `Schema` DDL outside migration helpers or workflows.
---

# SeaORM Schema Statements

`Schema` derives SeaQuery DDL from entity metadata outside migrations. Get backend from connection; build every statement with it.

## Entity-Derived DDL Order

For entities: 1) build, deduplicate, execute `create_enum_from_entity` statements; 2) execute `create_table_from_entity`; 3) execute each `create_index_from_entity` statement after its table. PostgreSQL enum types must precede referencing tables; indexes follow tables.

```rust
use sea_orm::{ConnectionTrait, DatabaseConnection, DbErr, Schema, Statement};

async fn create_schema(db: &DatabaseConnection) -> Result<(), DbErr> {
    let backend = db.get_database_backend();
    let schema = Schema::new(backend);
    let mut created_enums: Vec<Statement> = Vec::new();

    for create_enum in schema
        .create_enum_from_entity(tea::Entity)
        .into_iter()
        .chain(schema.create_enum_from_entity(order::Entity))
    {
        let statement = backend.build(&create_enum);
        if !created_enums.iter().any(|created| created == &statement) {
            db.execute(statement.clone()).await?;
            created_enums.push(statement);
        }
    }

    for create_table in [
        schema.create_table_from_entity(tea::Entity),
        schema.create_table_from_entity(order::Entity),
    ] {
        db.execute(backend.build(&create_table)).await?;
    }

    for create_index in schema
        .create_index_from_entity(tea::Entity)
        .into_iter()
        .chain(schema.create_index_from_entity(order::Entity))
    {
        db.execute(backend.build(&create_index)).await?;
    }

    Ok(())
}
```

`create_enum_from_entity` is empty on MySQL and SQLite: no PostgreSQL `CREATE TYPE` there. MySQL stores native enums in table definitions; SQLite has no standalone native enum type.

## Native Enums

String and integer `DeriveActiveEnum` values are ordinary database columns:

```rust
use sea_orm::entity::prelude::*;

#[derive(Debug, Clone, PartialEq, Eq, EnumIter, DeriveActiveEnum)]
#[sea_orm(rs_type = "String", db_type = "String(StringLen::N(1))")]
enum Category {
    #[sea_orm(string_value = "B")]
    Big,
    #[sea_orm(string_value = "S")]
    Small,
}
```

A native enum has `db_type = "Enum"` and `enum_name`. `create_enum_from_entity(entity)` returns all PostgreSQL type statements, empty on MySQL/SQLite. `create_enum_from_active_enum::<Tea>()` returns `Some` on PostgreSQL, `None` otherwise:

```rust
if let Some(create_enum) = schema.create_enum_from_active_enum::<Tea>() {
    db.execute(backend.build(&create_enum)).await?;
}
```

Use entity-wide or single-type form per type, never both. Execute before every referencing table.

## Indexes

`create_table_from_entity` creates columns, primary key, foreign keys—not entity-derived indexes. `#[sea_orm(indexed)]`, `#[sea_orm(unique)]`, and matching `#[sea_orm(unique_key = "name")]` use `create_index_from_entity`; matching `unique_key`s form one composite unique index.

```rust
let create_table = schema.create_table_from_entity(user::Entity);
db.execute(backend.build(&create_table)).await?;

for create_index in schema.create_index_from_entity(user::Entity) {
    db.execute(backend.build(&create_index)).await?;
}
```

`create_table_with_index_from_entity` is one-statement convenience when inline table indexes suit backend/caller. Use it instead of separate index loop. Prefer separate statements for ordering, inspection, or independent index handling.

For indexes not expressible as entity attributes:

```rust
use sea_orm::sea_query::Index;

let create = Index::create()
    .name("idx-post-slug")
    .table(post::Entity)
    .col(post::Column::Slug)
    .unique()
    .to_owned();
db.execute(backend.build(&create)).await?;
```

## Reference

- https://www.sea-ql.org/SeaORM/docs/schema-statement/create-table/
- https://www.sea-ql.org/SeaORM/docs/schema-statement/create-enum/
- https://www.sea-ql.org/SeaORM/docs/schema-statement/create-index/
