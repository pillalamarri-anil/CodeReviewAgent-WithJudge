# Persistence schema

Every entity extends `BaseModel(id BIGINT PK, created_at, last_modified_at)`.

## booking
| column  | type          | notes                                |
| ------- | ------------- | ------------------------------------ |
| id      | bigint        | PK                                   |
| user_id | bigint        | FK -> user(id), not null             |
| amount  | numeric(12,2) | money -- **must map to BigDecimal**  |
| status  | int           | ordinal of BookingStatus enum        |

## booking_show_seat  (join table, @ManyToMany)
`booking_id bigint FK`, `show_seat_id bigint FK`

Notes:
- `BookingRepository` is the only writer of `booking`.
- `Show_SeatRepository.updateShowSeats` bulk-updates seat status inside the booking transaction.
