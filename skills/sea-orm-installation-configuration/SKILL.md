---
name: sea-orm-installation-configuration
description: Use when configuring SeaORM's Cargo database driver and runtime, connection pool, or SQL statement logging in a Rust application.
---

# SeaORM Installation & Configuration

Choose matching Cargo features, configure one long-lived pool before connecting, and make statement logging an explicit development choice.

## Feature Selection

Choose needed database driver(s) and exactly one compatible Tokio runtime:

- MySQL or MariaDB: `sqlx-mysql` + `runtime-tokio-native-tls` or `runtime-tokio-rustls`
- Postgres: `sqlx-postgres` + `runtime-tokio-native-tls` or `runtime-tokio-rustls`
- SQLite-only: `sqlx-sqlite` + `runtime-tokio`
- Generated entities: `macros`

`runtime-tokio` is SQLite-only. A network backend needs one TLS runtime; never enable both merely as fallbacks. Add multiple drivers only when deployed binary supports multiple backends.

```toml
[dependencies]
sea-orm = { version = "2.0.0", features = [
  "sqlx-postgres",
  "runtime-tokio-rustls",
  "macros",
] }
```

## Pool Ownership and Lifecycle

`DatabaseConnection` owns a SQLx pool. Configure `ConnectOptions` before `Database::connect`; operations acquire and release pooled connections, so independent awaited queries can run in parallel.

```rust
use std::time::Duration;
use sea_orm::{ConnectOptions, Database, DatabaseConnection};

pub async fn connect(url: &str) -> Result<DatabaseConnection, sea_orm::DbErr> {
    let mut options = ConnectOptions::new(url);
    options
        .max_connections(100)
        .min_connections(5)
        .connect_timeout(Duration::from_secs(8))
        .acquire_timeout(Duration::from_secs(8))
        .idle_timeout(Duration::from_secs(8))
        .max_lifetime(Duration::from_secs(8));
    Database::connect(options).await
}
```

Keep `min_connections <= max_connections`; size pools for service concurrency and database capacity, not by copying a network-service pool size into SQLite. Use driver URL, for example `sqlite://path/to/db.sqlite?mode=rwc`, to create a missing file. Pool closes on drop; use `db.ping().await` for health checks and `db.close().await?` once at controlled shutdown, never after each request.

## Statement Logging

`debug-print` is a build feature that renders bound values in SeaORM SQL logs. Enable only for intended development/debug builds with safe-to-disclose data:

```toml
sea-orm = { version = "2.0.0", features = ["debug-print"] }
tracing = "0.1"
tracing-subscriber = "0.3"
```

Install one tracing subscriber in application entry point before database work. Libraries never install a global subscriber. If embedding can preinstall one, use `try_init()` and handle its result; never ignore an existing subscriber.

```rust
tracing_subscriber::fmt()
    .with_max_level(tracing::Level::DEBUG)
    .init();
```

SQLx logs separately by default. With `debug-print`, disable SQLx logging on that same pre-connect options value to prevent duplicate statements:

```rust
options.sqlx_logging(false);
```

Do not disable SQLx logging only because a subscriber exists; do it only when replacing SQLx output with SeaORM's readable, value-interpolated output.

## Reference

Use source pages for SeaORM API details and version-specific changes:

- https://www.sea-ql.org/SeaORM/docs/install-and-config/database-and-async-runtime/
- https://www.sea-ql.org/SeaORM/docs/install-and-config/connection/
- https://www.sea-ql.org/SeaORM/docs/install-and-config/debug-log/
