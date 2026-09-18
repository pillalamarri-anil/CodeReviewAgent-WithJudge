# Sample Service — Architecture

Layered Spring Boot service:

- **service/**    — transactional business logic.
- **repository/** — Spring Data JPA interfaces, one per aggregate root.

Money is always `BigDecimal`.
