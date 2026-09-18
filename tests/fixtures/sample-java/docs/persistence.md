---
applies_to: ["**/repository/**", "**/*Repository.java"]
---
# Persistence conventions

- Every repository interface is annotated `@Repository` and extends `JpaRepository<T, Long>`.
- Custom finders return `Optional<T>` — never `null`.
- No `@Query(nativeQuery = true)`; no string-concatenated JPQL.
