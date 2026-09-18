# BookMyShow -- Architecture

Layered Spring Boot service:

- **Controllers/** - thin REST adapters. No business logic, no repository access.
- **Services/**    - transactional business logic (booking, payment, sign-up, pricing).
- **Repositories/**- Spring Data JPA interfaces, one per aggregate root.
- **Models/**      - JPA entities extending `BaseModel` (id + timestamps).
- **dtos/**        - request / response payloads; entities never cross the wire.

Booking flow: `BookingController -> BookingService.book() -> { UserRepository, ShowRepository,
Show_SeatRepository, BookingRepository, PriceCalculationService, PaymentService }`, all inside a
single `SERIALIZABLE` transaction.
