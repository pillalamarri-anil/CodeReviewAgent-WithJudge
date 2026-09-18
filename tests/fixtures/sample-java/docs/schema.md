# Persistence schema

## orders
| column      | type          | notes                              |
| ----------- | ------------- | ---------------------------------- |
| id          | bigint        | PK                                 |
| customer_id | bigint        | FK -> customer(id), not null       |
| amount      | numeric(12,2) | money — must map to BigDecimal     |
