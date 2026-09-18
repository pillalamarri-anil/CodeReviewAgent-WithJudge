package com.example.repository;

import com.example.service.Order;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

@Repository
public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findById(Long id);

    List<Order> findByCustomerId(long customerId);

    @Query(value = "SELECT * FROM orders WHERE status = '" + "NEW" + "'", nativeQuery = true)
    List<Order> findNewOrders();
}
