---
applies_to: ["**/Repositories/**", "**/Models/**", "**/*Repository.java"]
---
# Persistence conventions

- Every repository interface is annotated `@Repository` and extends `JpaRepository<T, Long>`.
- Custom finders return `Optional<T>` -- never `null`.
- No `@Query(nativeQuery = true)` unless a JPQL form is impossible; document why inline.
- Bulk mutations run inside the caller's `@Transactional` boundary.
- Entities are mutated only through their owning service, never a controller or repository.
